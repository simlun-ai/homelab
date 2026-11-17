"""Deliver the enrolled Trust ZFS key over authenticated Kubernetes exec."""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trust_talos_recovery as recovery  # noqa: E402
import trust_zfs_key as zfs  # noqa: E402

NODE = "10.10.0.10"
HOSTNAME = "trust-cp1"
KEY_DIRECTORY = "/var/lib/trust-zfs/keys"
IMAGE = "docker.io/library/python@sha256:9cf2fdca7b3dd6082fd160ff5b8664f108c7441e200018a36554b2e8028f45df"
RECEIVER = Path(__file__).with_name("trust_zfs_key_receiver.py")


def deliver(kubectl: str, kubeconfig: bytes, unwrap: str) -> None:
    namespace = "trust-zfs-key-" + uuid4().hex[:12]
    source = RECEIVER.read_text()

    def kub(*args: str, payload: bytes | None = None, timeout: int = 30) -> None:
        with recovery.config.memory_file(kubeconfig) as fd:
            subprocess.run(
                [
                    kubectl,
                    "--kubeconfig",
                    f"/proc/self/fd/{fd}",
                    "-n",
                    namespace,
                    *args,
                ],
                pass_fds=(fd,),
                # Secret payloads go only to stdin, outside the child argv.
                input=payload,
                timeout=timeout,
                check=True,
            )

    def create(kind: str, metadata: dict[str, object], **fields: object) -> None:
        data = {"apiVersion": "v1", "kind": kind, "metadata": metadata, **fields}
        kub("create", "-f", "-", payload=json.dumps(data).encode())

    create(
        "Namespace",
        {
            "name": namespace,
            "labels": {"pod-security.kubernetes.io/enforce": "privileged"},
        },
    )
    try:
        create(
            "Pod",
            {"name": "receiver", "namespace": namespace},
            spec={
                "nodeName": HOSTNAME,
                "restartPolicy": "Never",
                "activeDeadlineSeconds": 480,
                "automountServiceAccountToken": False,
                "securityContext": {
                    "runAsUser": 0,
                    "runAsGroup": 0,
                    "seccompProfile": {"type": "RuntimeDefault"},
                },
                "containers": [
                    {
                        "name": "receiver",
                        "image": IMAGE,
                        "command": [
                            "python3",
                            "-I",
                            "-B",
                            "-c",
                            "import time; time.sleep(480)",
                        ],
                        "securityContext": {
                            "allowPrivilegeEscalation": False,
                            "readOnlyRootFilesystem": True,
                            "capabilities": {"drop": ["ALL"]},
                        },
                        "volumeMounts": [
                            {"name": "key-directory", "mountPath": "/key-directory"}
                        ],
                    }
                ],
                "volumes": [
                    {
                        "name": "key-directory",
                        "hostPath": {
                            "path": KEY_DIRECTORY,
                            "type": "DirectoryOrCreate",
                        },
                    }
                ],
            },
        )
        kub(
            "wait",
            "--for=condition=Ready",
            "pod/receiver",
            "--timeout=120s",
            timeout=130,
        )
        kub("exec", "receiver", "--", "python3", "-I", "-B", "-c", source, "check")
        print("Touch the YubiKey to recover the enrolled ZFS key.", flush=True)
        key = zfs.recover(unwrap)
        kub(
            "exec",
            "-i",
            "receiver",
            "--",
            "python3",
            "-I",
            "-B",
            "-c",
            source,
            "install",
            payload=key,
        )
    finally:
        kub("delete", "namespace", namespace, "--timeout=60s", timeout=70)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("talosctl", "kubectl", "unwrap"):
        parser.add_argument(f"--{argument}", type=Path, required=True)
    args = parser.parse_args()
    secrets = recovery.secrets
    try:
        secrets.harden()
        secrets.require_private_repository(record=zfs.RECORD)
        if not zfs.RECORD.is_file() or zfs.RECORD.is_symlink():
            raise secrets.PreflightError("Existing wrapped ZFS key is required")
        talosctl = secrets.executable(args.talosctl, "talosctl")
        kubectl = secrets.executable(args.kubectl, "kubectl")
        unwrap = secrets.executable(args.unwrap, "homelab-unwrap")
        print("Touch the YubiKey to recover the Trust Talos identity.", flush=True)
        bundle = secrets.recover_bundle(
            unwrap, record=secrets.RECORD, key_id=secrets.KEY_ID
        )
        ca, key = recovery.talos_ca(bundle)
        client = recovery.credentials.issue(
            talosctl,
            ca,
            key,
            Path("/dev/shm"),
            context="trust",
            node=NODE,
        )
        with recovery.config.memory_file(client) as fd:
            kubeconfig = secrets.capture_bundle(
                [
                    talosctl,
                    "kubeconfig",
                    "-",
                    "--merge=false",
                    "--talosconfig",
                    f"/proc/self/fd/{fd}",
                    "--endpoints",
                    NODE,
                    "--nodes",
                    NODE,
                ],
                timeout=30,
                pass_fds=(fd,),
            )
        deliver(kubectl, kubeconfig, unwrap)
    except secrets.PreflightError as exc:
        print(f"ZFS key delivery preflight failed: {exc}", file=sys.stderr)
        return 1
    except (
        OSError,
        RuntimeError,
        ValueError,
        subprocess.SubprocessError,
        KeyboardInterrupt,
    ):
        print(
            "ZFS key delivery failed or was interrupted. Check the last stage and temporary namespace.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
