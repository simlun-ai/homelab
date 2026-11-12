"""Run the locked Trust KMS service with explicit TLS authorization."""

import argparse
import json
import os
import signal
import socket
import sys
import threading
from pathlib import Path
from typing import cast
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))

from homelab.trust_kms import control, daemon, envelope, registration, session, tls  # noqa: E402

DEFAULT_SOCKET = Path("/run/trust-kms/control.sock")
VM_NODE = "5c73da99-dfe7-48b3-8687-5d0b46dbe647"
VM_KEY_ID = "homelab/v1/trust/kms/qemu-rehearsal/r1"
VM_WINDOW_SECONDS = 600


def serve_locked(
    path: Path,
    *,
    tls_path: Path | None = None,
    address: str = tls.ADDRESS,
    ca_file: Path = tls.CA_FILE,
    vm_rehearsal: bool = False,
) -> None:
    tls.harden_process()
    stop = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    authority = (
        daemon.Authority(
            {VM_NODE: session.Policy(frozenset({VM_KEY_ID}), VM_KEY_ID)},
            max_window_seconds=VM_WINDOW_SECONDS,
        )
        if vm_rehearsal
        else daemon.Authority(
            {
                registration.NODE: session.Policy(
                    frozenset({registration.KEY_ID}), registration.KEY_ID
                )
            }
        )
    )
    listener = tls.Listener(authority, address=address, ca_file=ca_file)
    with (
        authority.run(),
        control.listen(authority, path, allowed_uids={0, os.geteuid()}),
        control.listen(
            authority,
            path.with_name("tls.sock") if tls_path is None else tls_path,
            allowed_uids={0, os.geteuid()},
            handler=listener.dispatch,
            frame_limit=tls.FRAME_LIMIT,
        ),
    ):
        try:
            while not stop.wait(0.25):
                listener.expire()
        finally:
            listener.close()


def request(
    path: Path, action: str, *, timeout: float = control.READ_TIMEOUT, **fields: object
) -> dict[str, object]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
        peer.settimeout(control.READ_TIMEOUT)
        peer.connect(str(path))
        control.send(peer, {"protocol": control.PROTOCOL, "action": action, **fields})
        return control.receive(peer, timeout=timeout)


def vm_window(path: Path, *, open_window: bool) -> None:
    if os.geteuid() != 0:
        raise ValueError("VM rehearsal control requires root")
    if not open_window:
        result = request(path, "lock-KMS")
        if result.get("state") != "locked" or result.get("authorized") != []:
            raise ValueError("KMS lock was not confirmed")
        print("PASS: KMS locked.")
        return

    tls.harden_process()
    tls.require_memory_policy()
    status = tls.local("status", socket_path=path.with_name("tls.sock"))
    if status.get("tls_state") != "active" or status.get("kms_state") != "locked":
        raise ValueError("Expected active TLS and locked KMS")
    result = request(
        path,
        "open-boot-window",
        timeout=10,
        expected_instance=envelope.node_uuid(status.get("instance")),
        request_id=str(uuid4()),
        grants=[
            {
                "node_uuid": VM_NODE,
                "key_id": VM_KEY_ID,
                "key": envelope.b64(os.urandom(32)),
            }
        ],
    )
    if result.get("state") != "active" or result.get("authorized") != [
        [VM_NODE, VM_KEY_ID]
    ]:
        raise ValueError("VM KMS window was not confirmed")
    print(f"PASS: disposable VM key authorized for up to {VM_WINDOW_SECONDS} seconds.")


def node_window(path: Path, action: str) -> None:
    if os.geteuid() != 0:
        raise ValueError("KMS control requires root")
    tls.harden_process()
    if action == "node-open":
        tls.require_memory_policy()
        raw = sys.stdin.buffer.read(1025)
        if len(raw) > 1024:
            raise ValueError("Oversized request")
        data: object = json.loads(raw, object_pairs_hook=envelope.unique)
        if not isinstance(data, dict) or data.keys() != {
            "instance",
            "request_id",
            "key",
        }:
            raise ValueError("Unexpected request")
        payload = cast(dict[str, object], data)
        status = tls.local("status", socket_path=path.with_name("tls.sock"))
        instance = envelope.node_uuid(payload["instance"])
        if status.get("instance") != instance or status.get("tls_state") != "active":
            raise ValueError("TLS is not active on the expected instance")
        key = payload["key"]
        if not isinstance(key, str):
            raise ValueError("Invalid key")
        envelope.decode(key, 32)
        result = request(
            path,
            "open-boot-window",
            timeout=10,
            expected_instance=instance,
            request_id=envelope.node_uuid(payload["request_id"]),
            grants=[
                {
                    "node_uuid": registration.NODE,
                    "key_id": registration.KEY_ID,
                    "key": key,
                }
            ],
        )
        if result.get("state") != "active" or result.get("authorized") != [
            [registration.NODE, registration.KEY_ID]
        ]:
            raise ValueError("Activation was not confirmed")
    else:
        result = request(
            path, "lock-KMS" if action == "node-lock" else "status", timeout=10
        )
        if action == "node-lock" and (
            result.get("state") != "locked" or result.get("authorized") != []
        ):
            raise ValueError("Lock was not confirmed")
    if result.get("error") is not None:
        raise ValueError("KMS request failed")
    fields = ("instance", "state", "request_id", "remaining", "authorized")
    print(json.dumps({field: result[field] for field in fields}))


def check_locked(path: Path) -> None:
    status = request(path, "status")
    if (
        status.get("protocol") != control.PROTOCOL
        or status.get("state") != "locked"
        or status.get("authorized") != []
        or status.get("remaining") != 0
    ):
        raise ValueError("KMS did not report a clean locked startup")
    # Print only known public fields, even if the peer sends unexpected keys.
    instance = envelope.node_uuid(status.get("instance"))
    tls_status = tls.local("status", socket_path=path.with_name("tls.sock"))
    if (
        tls_status.get("instance") != instance
        or tls_status.get("kms_state") != "locked"
        or tls_status.get("tls_state") not in ("disabled", "active")
    ):
        raise ValueError("TLS status does not match locked KMS instance")
    print(
        json.dumps(
            {
                "state": "locked",
                "instance": instance,
                "listener": tls_status["tls_state"],
            }
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=(
            "serve-locked",
            "status",
            "vm-open",
            "vm-lock",
            "node-open",
            "node-lock",
            "node-status",
        ),
    )
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET)
    parser.add_argument("--vm-rehearsal", action="store_true")
    args = parser.parse_args()
    if args.vm_rehearsal and args.action != "serve-locked":
        parser.error("--vm-rehearsal requires serve-locked")
    path: Path = args.socket
    try:
        if args.action == "serve-locked":
            serve_locked(path, vm_rehearsal=args.vm_rehearsal)
        elif args.action == "status":
            check_locked(path)
        elif args.action.startswith("node-"):
            node_window(path, args.action)
        else:
            vm_window(path, open_window=args.action == "vm-open")
    except (OSError, ValueError):
        print("Trust KMS command failed. Check service state.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
