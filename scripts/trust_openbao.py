"""Initialize and unseal the staged Trust OpenBao server through Kubernetes exec."""

import argparse
import base64
import hmac
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trust_tofu as tofu  # noqa: E402
import trust_tofu_key as tofu_key  # noqa: E402

secrets = tofu.recovery.secrets
RECORDS = tofu.ROOT / "secrets/wrapped"
UNSEAL = (
    RECORDS / "trust-openbao-unseal-share-1-r1.json",
    "homelab/v1/trust/openbao-unseal/share-1/r1",
)
ROOT_TOKEN = (
    RECORDS / "trust-openbao-initial-root-token-r1.json",
    "homelab/v1/trust/openbao-bootstrap/initial-root-token/r1",
)
TLS_OPTIONS = (
    "-address=https://127.0.0.1:8200",
    "-tls-server-name=bao.k8s-aux.simlun.se",
    "-tls-skip-verify=false",
    "-disable-redirects",
)


def status(command: list[str], fd: int) -> tuple[bool, bool]:
    result = subprocess.run(
        [
            *command,
            "--",
            "bao",
            "status",
            "-format=json",
            "-non-interactive",
            *TLS_OPTIONS,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        pass_fds=(fd,),
        timeout=30,
        check=False,
    )
    if result.returncode not in (0, 2):
        raise ValueError("Could not read OpenBao status over verified TLS")
    data: object = json.loads(result.stdout)
    match data:
        case {
            "type": "shamir",
            "initialized": bool(initialized),
            "sealed": bool(sealed),
        }:
            if (result.returncode == 2) == sealed:
                return initialized, sealed
        case _:
            pass
    raise ValueError("Unexpected OpenBao seal status")


def parse_initialization(raw: bytes) -> tuple[bytes, bytes]:
    data: object = json.loads(raw)
    match data:
        case {
            "unseal_keys_b64": [str(share)],
            "unseal_shares": 1,
            "unseal_threshold": 1,
            "root_token": str(token),
        }:
            decoded = base64.b64decode(share, validate=True)
            if (
                decoded
                and len(token) <= 1024
                and token
                and all("!" <= c <= "~" for c in token)
            ):
                return share.encode("ascii"), token.encode("ascii")
        case _:
            pass
    raise ValueError("Unexpected OpenBao initialization response")


def store_record(
    record: tuple[Path, str], value: bytes, wrap: str, unwrap: str, tty: int
) -> None:
    path, key_id = record
    while True:
        try:
            if not os.path.lexists(path):
                secrets.wrap_bundle(value, wrap, record=path, key_id=key_id, stderr=tty)
            recovered = secrets.recover_bundle(
                unwrap, record=path, key_id=key_id, stderr=tty
            )
        except (
            OSError,
            ValueError,
            RuntimeError,
            subprocess.SubprocessError,
            KeyboardInterrupt,
        ):
            print(
                f"Could not store or verify {path.name}. Correct the problem first.",
                file=sys.stderr,
            )
        else:
            if hmac.compare_digest(value, recovered):
                print(f"PASS: verified {path.name}.", flush=True)
                return
            print(
                f"{path.name} differs from the new credential. Check the record path.",
                file=sys.stderr,
            )
        with open("/dev/tty", encoding="utf-8") as terminal:
            print(
                "Press Enter to retry while the credentials are still in memory.",
                file=sys.stderr,
            )
            try:
                if not terminal.readline():
                    raise RuntimeError("Operator terminal closed")
            except KeyboardInterrupt:
                continue


def initialize(command: list[str], fd: int, wrap: str, unwrap: str, tty: int) -> None:
    if any(os.path.lexists(path) for path, _ in (UNSEAL, ROOT_TOKEN)):
        raise ValueError("A bootstrap record already exists")
    if status(command, fd) != (False, True):
        raise ValueError("OpenBao is already initialized")
    print(
        "Touch the YubiKey to verify your wrapped workload state key before initialization.",
        flush=True,
    )
    tofu_key.recover(unwrap, tofu_key.StateScope.WORKLOAD)
    args = [
        *command,
        "--",
        "bao",
        "operator",
        "init",
        "-format=json",
        "-key-shares=1",
        "-key-threshold=1",
        "-non-interactive",
        *TLS_OPTIONS,
    ]
    print(
        "Initializing Trust OpenBao. Keep this process running until both records verify.",
        flush=True,
    )
    share, token = parse_initialization(
        secrets.capture_bundle(args, timeout=120, pass_fds=(fd,))
    )
    store_record(UNSEAL, share, wrap, unwrap, tty)
    store_record(ROOT_TOKEN, token, wrap, unwrap, tty)
    print(
        "PASS: initialized OpenBao and independently verified both wrapped records.",
        flush=True,
    )


def unseal(command: list[str], fd: int, unwrap: str, tty: int) -> None:
    initialized, sealed = status(command, fd)
    if not initialized:
        raise ValueError("OpenBao must be initialized before unsealing")
    if not sealed:
        print("PASS: OpenBao is already unsealed.", flush=True)
        return
    print("Touch the YubiKey to recover the OpenBao unseal share.", flush=True)
    path, key_id = UNSEAL
    share = secrets.recover_bundle(unwrap, record=path, key_id=key_id, stderr=tty)
    if not base64.b64decode(share, validate=True):
        raise ValueError("Empty unseal share")
    args = [
        *command,
        "-i",
        "--",
        "bao",
        "write",
        "-format=json",
        *TLS_OPTIONS,
        "sys/unseal",
        "-",
    ]
    subprocess.run(
        args,
        input=json.dumps({"key": share.decode("ascii")}).encode(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        pass_fds=(fd,),
        timeout=30,
        check=True,
    )
    if status(command, fd) != (True, False):
        raise ValueError("OpenBao is still sealed")
    print("PASS: OpenBao is initialized and unsealed.", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("initialize", "unseal", "status"))
    parser.add_argument("--ram-root", type=Path, default=Path("/dev/shm"))
    args = parser.parse_args()
    try:
        secrets.harden()
        os.umask(0o077)
        if args.action != "status":
            for record, _ in (UNSEAL, ROOT_TOKEN):
                secrets.require_private_repository(record=record)
        kubectl = secrets.executable(tofu.SCOPE / "bin/kubectl", "kubectl")
        kubeconfig = tofu.get_kubeconfig(args.ram_root)
        with tofu.recovery.config.memory_file(kubeconfig) as fd:
            command = [
                kubectl,
                "--kubeconfig",
                f"/proc/self/fd/{fd}",
                "-n",
                "openbao",
                "exec",
                "pod/openbao-0",
                "-c",
                "openbao",
            ]
            if args.action == "status":
                initialized, sealed = status(command, fd)
                print(f"Initialized: {initialized}. Sealed: {sealed}.", flush=True)
                return 0
            bin_dir = Path(sys.executable).parent
            unwrap = secrets.executable(bin_dir / "homelab-unwrap", "homelab-unwrap")
            with open("/dev/tty", "w", encoding="utf-8") as tty:
                if args.action == "initialize":
                    wrap = secrets.executable(bin_dir / "homelab-wrap", "homelab-wrap")
                    initialize(command, fd, wrap, unwrap, tty.fileno())
                else:
                    unseal(command, fd, unwrap, tty.fileno())
    except (
        OSError,
        RuntimeError,
        ValueError,
        subprocess.SubprocessError,
        KeyboardInterrupt,
    ):
        print(
            "Trust OpenBao operation stopped. Check status and the runbook before retrying.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
