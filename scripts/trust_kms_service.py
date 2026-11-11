"""Run the locked Trust KMS service with explicit TLS authorization."""

import argparse
import json
import os
import signal
import socket
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from homelab.trust_kms import control, daemon, envelope, tls  # noqa: E402

DEFAULT_SOCKET = Path("/run/trust-kms/control.sock")


def serve_locked(
    path: Path,
    *,
    tls_path: Path | None = None,
    address: str = tls.ADDRESS,
    ca_file: Path = tls.CA_FILE,
) -> None:
    tls.harden_process()
    stop = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    authority = daemon.Authority({})
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


def check_locked(path: Path) -> None:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
        peer.settimeout(control.READ_TIMEOUT)
        peer.connect(str(path))
        control.send(peer, {"protocol": control.PROTOCOL, "action": "status"})
        status = control.receive(peer)
    if (
        status.get("protocol") != control.PROTOCOL
        or status.get("state") != "locked"
        or status.get("authorized") != []
        or status.get("request_id") is not None
        or status.get("session_id") is not None
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
    parser.add_argument("action", choices=("serve-locked", "status"))
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET)
    args = parser.parse_args()
    path: Path = args.socket
    try:
        if args.action == "serve-locked":
            serve_locked(path)
        else:
            check_locked(path)
    except (OSError, ValueError):
        print("Trust KMS service or locked status check failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
