"""Run and inspect the locked Trust KMS staging service."""

import argparse
import json
import os
import signal
import socket
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from homelab.trust_kms import control, daemon, envelope  # noqa: E402

DEFAULT_SOCKET = Path("/run/trust-kms/control.sock")


def serve_locked(path: Path) -> None:
    stop = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    authority = daemon.Authority({})
    with (
        authority.run(),
        control.listen(authority, path, allowed_uids={0, os.geteuid()}),
    ):
        stop.wait()


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
    print(json.dumps({"state": "locked", "instance": instance, "listener": "disabled"}))


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
        print(
            "Trust KMS locked staging service or status check failed.", file=sys.stderr
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
