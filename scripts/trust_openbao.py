"""Initialize and unseal the staged Trust OpenBao server through Kubernetes exec."""

import argparse
import base64
import hmac
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

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


RESTORE_TLS_OPTIONS = tuple(
    "-ca-cert=/openbao/tls/ca.crt" if option.startswith("-tls-server-name=") else option
    for option in TLS_OPTIONS
)
BACKUP_RECORDS = {
    name: (
        RECORDS / f"trust-openbao-{name}-r1.json",
        f"homelab/v1/trust/openbao-backup/{name}/r1",
    )
    for name in ("restic-password", "r2-writer", "r2-reader")
}


def status(
    command: list[str], fd: int, tls_options: tuple[str, ...] = TLS_OPTIONS
) -> tuple[bool, bool]:
    result = subprocess.run(
        [
            *command,
            "--",
            "bao",
            "status",
            "-format=json",
            "-non-interactive",
            *tls_options,
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


def unseal(
    command: list[str],
    fd: int,
    unwrap: str,
    tty: int,
    tls_options: tuple[str, ...] = TLS_OPTIONS,
) -> None:
    initialized, sealed = status(command, fd, tls_options)
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
        *tls_options,
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
    if status(command, fd, tls_options) != (True, False):
        raise ValueError("OpenBao is still sealed")
    print("PASS: OpenBao is initialized and unsealed.", flush=True)


def restore_credentials(kubectl: list[str], fd: int, unwrap: str, tty: int) -> None:
    repository = os.environ.get("R2_REPOSITORY", "")
    if not re.fullmatch(
        r"s3:https://[a-f0-9]{32}(?:\.eu)?\.r2\.cloudflarestorage\.com/[a-z0-9-]+(?:/[A-Za-z0-9_-]+)+",
        repository,
    ):
        raise ValueError("Specify the private R2 repository URL")
    wrapped: dict[str, bytes] = {}
    for name, (record, key_id) in BACKUP_RECORDS.items():
        secrets.require_private_repository(record=record)
        print(f"Touch the YubiKey to recover {name}.", flush=True)
        wrapped[name] = secrets.recover_bundle(
            unwrap, record=record, key_id=key_id, stderr=tty
        )
    for role, namespace, name in (
        ("writer", "openbao", "openbao-backup-r2"),
        ("reader", "openbao-restore", "openbao-restore-r2"),
    ):
        credential: object = json.loads(wrapped[f"r2-{role}"])
        match credential:
            case {"access-key-id": str(access), "secret-access-key": str(secret)} if (
                access and secret
            ):
                values = {
                    "access-key-id": access.encode(),
                    "secret-access-key": secret.encode(),
                    "password": wrapped["restic-password"],
                    "repository": repository.encode(),
                }
            case _:
                raise ValueError("Invalid wrapped R2 credentials")
        document = {
            "apiVersion": "v1",
            "kind": "Secret",
            "type": "Opaque",
            "metadata": {"name": name, "namespace": namespace},
            "data": {
                key: base64.b64encode(value).decode() for key, value in values.items()
            },
        }
        subprocess.run(
            [*kubectl, "apply", "--server-side", "-f", "-"],
            input=json.dumps(document).encode(),
            pass_fds=(fd,),
            check=True,
            timeout=30,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"Configured {namespace}/{name}.", flush=True)


def configure_auth(
    command: list[str], fd: int, unwrap: str, tty: int, script: Path, *args: str
) -> None:
    path, key_id = ROOT_TOKEN
    secrets.require_private_repository(record=path)
    print("Touch the YubiKey for the production OpenBao bootstrap token.", flush=True)
    token = secrets.recover_bundle(unwrap, record=path, key_id=key_id, stderr=tty)
    subprocess.run(
        [*command, "-i", "--", "sh", "-ec", script.read_text(), "bootstrap", *args],
        input=token + b"\n",
        pass_fds=(fd,),
        check=True,
        timeout=45,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def init_restic_repository(kube: list[str], fd: int) -> None:
    namespace = [*kube, "-n", "openbao"]
    name = "openbao-restic-init"
    manifest = subprocess.check_output(
        [
            *namespace,
            "create",
            "job",
            name,
            "--from=cronjob/openbao-backup",
            "--dry-run=client",
            "-o",
            "json",
        ],
        pass_fds=(fd,),
        timeout=30,
    )
    job = cast(dict[str, Any], json.loads(manifest))
    spec = job["spec"]
    pod = spec["template"]["spec"]
    pod["containers"][0]["args"] = ["init"]
    pod["initContainers"] = [c for c in pod["initContainers"] if c["name"] != "bao"]
    pod["containers"][0]["volumeMounts"] = [
        m for m in pod["containers"][0]["volumeMounts"] if m["name"] != "identity"
    ]
    pod["volumes"] = [v for v in pod["volumes"] if v["name"] != "identity"]
    spec["ttlSecondsAfterFinished"] = 86400
    subprocess.run(
        [*namespace, "create", "-f", "-"],
        input=json.dumps(job).encode(),
        pass_fds=(fd,),
        timeout=30,
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=(
            "initialize",
            "unseal",
            "status",
            "restore-unseal",
            "restore-shell",
            "jobs-credentials",
            "backup-init-repo",
            "backup-auth",
            "kms-auth",
            "kubectl",
        ),
    )
    parser.add_argument("--ram-root", type=Path, default=Path("/dev/shm"))
    args = parser.parse_args()
    try:
        secrets.harden()
        os.umask(0o077)
        if args.action in ("initialize", "unseal", "restore-unseal"):
            for record, _ in (UNSEAL, ROOT_TOKEN):
                secrets.require_private_repository(record=record)
        kubectl = secrets.executable(tofu.SCOPE / "bin/kubectl", "kubectl")
        kubeconfig = tofu.get_kubeconfig(args.ram_root)
        with tofu.recovery.config.memory_file(kubeconfig) as fd:
            kube = [kubectl, "--kubeconfig", f"/proc/self/fd/{fd}"]
            if args.action == "kubectl":
                argv = shlex.split(os.environ.get("KUBECTL_ARGS", ""))
                return subprocess.run(
                    [*kube, *argv], pass_fds=(fd,), check=False
                ).returncode
            if args.action == "backup-init-repo":
                init_restic_repository(kube, fd)
                return 0
            restore = args.action in ("restore-unseal", "restore-shell")
            namespace = "openbao-restore" if restore else "openbao"
            command = [
                *kube,
                "-n",
                namespace,
                "exec",
                f"pod/{namespace}-0",
                "-c",
                "openbao",
            ]
            if args.action == "restore-shell":
                return subprocess.run(
                    [*command, "-it", "--", "/bin/sh"], pass_fds=(fd,), check=False
                ).returncode
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
                elif args.action == "jobs-credentials":
                    restore_credentials(kube, fd, unwrap, tty.fileno())
                elif args.action == "backup-auth":
                    configure_auth(
                        command,
                        fd,
                        unwrap,
                        tty.fileno(),
                        tofu.SCOPE
                        / "helm/charts/openbao-jobs/scripts/bootstrap-auth.sh",
                    )
                    print(
                        "Configured the production snapshot policy and Kubernetes login.",
                        flush=True,
                    )
                elif args.action == "kms-auth":
                    cluster = os.environ.get("KMS_CLUSTER", "")
                    if not re.fullmatch(r"[a-z][a-z0-9-]{0,30}", cluster):
                        raise ValueError(
                            "Set KMS_CLUSTER to the registered cluster name"
                        )
                    configure_auth(
                        command,
                        fd,
                        unwrap,
                        tty.fileno(),
                        tofu.SCOPE / "openbao-kms-bootstrap.sh",
                        cluster,
                    )
                    print(
                        f"Configured OpenBao Transit and Kubernetes login for {cluster}.",
                        flush=True,
                    )
                elif restore:
                    unseal(command, fd, unwrap, tty.fileno(), RESTORE_TLS_OPTIONS)
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
