"""Operate the scheduled Trust OpenBao backup and manual YubiKey restore check."""

import argparse
import base64
import copy
import getpass
import http.client
import json
import os
import re
import secrets as random
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, cast

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trust_openbao as openbao  # noqa: E402
import trust_tofu as tofu  # noqa: E402

secrets = tofu.recovery.secrets
SCOPE = tofu.SCOPE / "openbao-backup"
NAMESPACE = "openbao-backup"
NAME = "openbao-backup"
TRACE_FIXTURE = "trust-openbao-restore-v1"
REPOSITORY = re.compile(
    r"s3:https://[a-f0-9]{32}\.r2\.cloudflarestorage\.com/"
    r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9](?:/[A-Za-z0-9_-]+)+"
)
RECORDS = {
    name: (
        openbao.RECORDS / f"trust-openbao-{name}-r1.json",
        f"homelab/v1/trust/openbao-backup/{name}/r1",
    )
    for name in ("restic-password", "r2-writer", "r2-reader")
}
RESOURCES = SCOPE / "resources.yaml"
Object = dict[str, Any]


def tool(name: str) -> str:
    return secrets.executable(Path(sys.executable).with_name(name), name)


def recover(record: tuple[Path, str], unwrap: str) -> bytes:
    path, key_id = record
    secrets.require_private_repository(record=path)
    with secrets.hsm_progress_terminal() as progress:
        return secrets.recover_bundle(
            unwrap, record=path, key_id=key_id, stderr=progress
        )


def enroll() -> None:
    wrap = tool("homelab-wrap")
    for name, (path, key_id) in RECORDS.items():
        secrets.require_private_repository(record=path)
        if os.path.lexists(path):
            print(f"Existing wrapped record: {path.name}", flush=True)
            continue
        if name == "restic-password":
            data = random.token_urlsafe(48).encode()
        else:
            a = getpass.getpass(f"{name} access key ID: ")
            b = getpass.getpass(f"{name} secret access key: ")
            if not (
                re.fullmatch(r"[A-Za-z0-9]{20,128}", a)
                and re.fullmatch(r"[A-Za-z0-9/+_=.-]{24,256}", b)
            ):
                raise ValueError("Invalid R2 credential format")
            data = json.dumps({"access-key-id": a, "secret-access-key": b}).encode()
        print(f"Touch the YubiKey to wrap {name}.", flush=True)
        with secrets.hsm_progress_terminal() as progress:
            secrets.wrap_bundle(data, wrap, record=path, key_id=key_id, stderr=progress)
        print(f"PASS: created {path.name}", flush=True)


class Kubernetes:
    def __init__(self, fd: int) -> None:
        self.fd = fd
        kubectl = secrets.executable(tofu.SCOPE / "bin/kubectl", "kubectl")
        self.base = [kubectl, "--kubeconfig", f"/proc/self/fd/{fd}", "-n", NAMESPACE]

    def run(self, *args: str, data: bytes | None = None, timeout: int = 40) -> bytes:
        result = subprocess.run(
            [*self.base, *args],
            input=data,
            pass_fds=(self.fd,),
            timeout=timeout,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode:
            raise ValueError(f"Kubernetes {args[0]} failed (exit {result.returncode})")
        return result.stdout

    def get(self, kind: str, name: str) -> Object:
        raw = self.run("get", kind, name, "--ignore-not-found", "-o", "json")
        return cast(Object, json.loads(raw)) if raw else {}

    def apply(self, obj: Object) -> None:
        # Server-side apply avoids a last-applied annotation containing secret data.
        self.run(
            "apply",
            "--server-side",
            "--field-manager=trust-openbao-backup",
            "-f",
            "-",
            data=json.dumps(obj).encode(),
        )


def resource(kind: str, name: str, **fields: Any) -> Object:
    version = "batch/v1" if kind == "Job" else "v1"
    return {
        "apiVersion": version,
        "kind": kind,
        "metadata": {"name": name, "namespace": NAMESPACE},
        **fields,
    }


def set_credentials(kube: Kubernetes, unwrap: str) -> None:
    password = recover(RECORDS["restic-password"], unwrap)
    for name in ("writer", "reader"):
        raw: object = json.loads(recover(RECORDS[f"r2-{name}"], unwrap))
        match raw:
            case {"access-key-id": str(access), "secret-access-key": str(secret)}:
                values = {
                    "password": password,
                    "access-key-id": access.encode(),
                    "secret-access-key": secret.encode(),
                }
            case _:
                raise ValueError(f"Malformed wrapped R2 {name} record")
        kube.apply(
            resource(
                "Secret",
                f"{NAME}-{name}",
                type="Opaque",
                data={
                    key: base64.b64encode(value).decode()
                    for key, value in values.items()
                },
            )
        )


def configure_openbao(root: str) -> None:
    conn = http.client.HTTPSConnection("bao.k8s-aux.simlun.se", timeout=20)

    def request(method: str, path: str, payload: Object | None = None) -> Object:
        conn.request(
            method,
            f"/v1/{path}",
            json.dumps(payload) if payload is not None else None,
            {"X-Vault-Token": root, "Content-Type": "application/json"},
        )
        response = conn.getresponse()
        raw = response.read(512 * 1024 + 1)
        if response.status not in (200, 204) or len(raw) > 512 * 1024:
            raise ValueError(
                f"OpenBao configuration failed at {path}: HTTP {response.status}"
            )
        return cast(Object, json.loads(raw)) if raw else {}

    try:
        policy = 'path "sys/storage/raft/snapshot" { capabilities = ["read", "sudo"] }'
        request("PUT", "sys/policies/acl/trust-raft-snapshot", {"policy": policy})
        mounts = request("GET", "sys/auth")["data"]
        if "trust-backup/" not in mounts:
            request("POST", "sys/auth/trust-backup", {"type": "kubernetes"})
        elif mounts["trust-backup/"]["type"] != "kubernetes":
            raise ValueError("Existing trust-backup auth mount has the wrong type")
        request(
            "POST",
            "auth/trust-backup/config",
            {
                "kubernetes_host": "https://kubernetes.default.svc:443",
            },
        )
        request(
            "POST",
            "auth/trust-backup/role/snapshot",
            {
                "bound_service_account_names": [NAME],
                "bound_service_account_namespaces": [NAMESPACE],
                "audience": "trust-openbao-backup",
                "token_policies": ["trust-raft-snapshot"],
                "token_no_default_policy": True,
                "token_ttl": "10m",
                "token_max_ttl": "10m",
            },
        )
        engines = request("GET", "sys/mounts")["data"]
        if "trust-backup-fixture/" not in engines:
            request(
                "POST",
                "sys/mounts/trust-backup-fixture",
                {"type": "kv", "options": {"version": "2"}},
            )
        elif (
            engines["trust-backup-fixture/"]["type"] != "kv"
            or engines["trust-backup-fixture/"]["options"]["version"] != "2"
        ):
            raise ValueError("Existing restore fixture mount is not KV v2")
        request(
            "POST",
            "trust-backup-fixture/data/restore",
            {"data": {"value": TRACE_FIXTURE}},
        )
    finally:
        conn.close()


def configure(kube: Kubernetes, repository: str, unwrap: str) -> None:
    if not REPOSITORY.fullmatch(repository):
        raise ValueError(
            "Specify a dedicated R2 s3:https://… repository URL with a path"
        )
    objects = cast(list[Object], list(yaml.safe_load_all(RESOURCES.read_text())))
    cron = objects.pop()
    current = kube.get("cronjob", NAME)
    old_settings = kube.get("configmap", f"{NAME}-settings")
    if old_settings and old_settings["data"]["RESTIC_REPOSITORY"] != repository:
        raise ValueError("Existing backup schedule uses another repository")
    if current and (
        not current["spec"].get("suspend", False)
        or current.get("status", {}).get("active")
    ):
        raise ValueError(
            "Suspend the schedule and let the active job finish before configuring"
        )

    for obj in objects:
        kube.apply(obj)
    set_credentials(kube, unwrap)
    print("Touch the YubiKey for the wrapped OpenBao bootstrap root token.", flush=True)
    configure_openbao(recover(openbao.ROOT_TOKEN, unwrap).decode("ascii"))
    kube.apply(
        resource(
            "ConfigMap",
            f"{NAME}-settings",
            data={
                "RESTIC_REPOSITORY": repository,
                "SNAPSHOT_MAX_BYTES": "67108864",
                "OPENBAO_VERSION": "2.7.3",
            },
        )
    )
    kube.apply(
        resource(
            "ConfigMap",
            f"{NAME}-pipeline",
            data={
                name: (SCOPE / name).read_text()
                for name in ("pipeline.py", "isolate.py")
            },
        )
    )
    kube.apply(cron)
    print(
        f"Backup configuration applied. Schedule suspended: {cron['spec']['suspend']}.",
        flush=True,
    )


def private_job(kube: Kubernetes, action: str, snapshot_id: str = "") -> str:
    cron = kube.get("cronjob", NAME)
    if not cron:
        raise ValueError("Configure OpenBao backups first")
    spec = copy.deepcopy(cron["spec"]["jobTemplate"]["spec"])
    pod = spec["template"]["spec"]
    stages = {item["name"]: item for item in pod["initContainers"]}
    worker = pod["containers"][0]
    if action in ("init-repo", "check-repo"):
        worker = stages["backup"]
        worker["args"] = [action]
        worker["volumeMounts"] = [
            m for m in worker["volumeMounts"] if m["name"] != "identity"
        ]
        pod["initContainers"] = [stages["stage-restic"]]
        omitted = {"identity", "reader"}
    else:
        worker["args"] = ["restore-hold"]
        stages["download"]["env"] = [
            {"name": "RESTORE_SNAPSHOT_ID", "value": snapshot_id}
        ]
        pod["initContainers"] = [
            stages[key] for key in ("stage-bao", "stage-restic", "download")
        ]
        omitted = {"writer", "identity"}
    pod["containers"] = [worker]
    pod["volumes"] = [v for v in pod["volumes"] if v["name"] not in omitted]
    spec["ttlSecondsAfterFinished"] = 86400
    name = f"{NAME}-{action}-{random.token_hex(4)}"
    kube.run(
        "create", "-f", "-", data=json.dumps(resource("Job", name, spec=spec)).encode()
    )
    print(f"Started Job {name}.", flush=True)
    return name


def wait_for_job(kube: Kubernetes, name: str) -> None:
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        job = kube.get("job", name)
        if job.get("status", {}).get("succeeded"):
            print(f"PASS: Job {name} completed.", flush=True)
            return
        if job.get("status", {}).get("failed"):
            raise ValueError(
                f"Job {name} failed. Use openbao-backup-status for details."
            )
        time.sleep(2)
    raise ValueError(f"Timed out waiting for Job {name}")


def verify(kube: Kubernetes, snapshot_id: str, unwrap: str) -> None:
    if not re.fullmatch("[0-9a-f]{64}", snapshot_id):
        raise ValueError("Specify the full verified restic snapshot ID")
    name = private_job(kube, "verify", snapshot_id)
    try:
        verify_job(kube, name, unwrap)
    except (OSError, ValueError, subprocess.SubprocessError, KeyboardInterrupt):
        try:
            kube.run("delete", "job", name, "--ignore-not-found", "--wait=false")
        except ValueError:
            print(f"Could not remove disposable Job {name}.", file=sys.stderr)
        raise
    print(f"PASS: restored OpenBao fixture matched for {snapshot_id}.", flush=True)


def verify_job(kube: Kubernetes, name: str, unwrap: str) -> None:
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        raw = kube.run("get", "pods", "-l", f"job-name={name}", "-o", "json")
        pods = cast(Object, json.loads(raw))["items"]
        if len(pods) == 1:
            pod = pods[0]["metadata"]["name"]
            try:
                kube.run(
                    "exec", pod, "-c", "restore", "--", "test", "-f", "/work/ready"
                )
            except ValueError:
                if kube.get("job", name).get("status", {}).get("failed"):
                    raise ValueError(
                        f"Restore Job {name} failed before unseal"
                    ) from None
            else:
                break
        time.sleep(3)
    else:
        raise ValueError(
            f"Restore Job {name} did not reach the sealed restore checkpoint"
        )
    print(
        "Touch the YubiKey for the source unseal share and wrapped root token.",
        flush=True,
    )
    data = json.dumps(
        {
            "share": recover(openbao.UNSEAL, unwrap).decode("ascii"),
            "token": recover(openbao.ROOT_TOKEN, unwrap).decode("ascii"),
        }
    ).encode()
    kube.run(
        "exec",
        "-i",
        pod,
        "-c",
        "restore",
        "--",
        "python3",
        "-I",
        "-B",
        "/pipeline/pipeline.py",
        "verify",
        data=data,
        timeout=160,
    )
    wait_for_job(kube, name)


def show_status(kube: Kubernetes) -> None:
    print(kube.run("get", "cronjobs,jobs").decode(), end="")
    raw = kube.run("get", "jobs", "-o", "json")
    jobs = cast(Object, json.loads(raw))["items"]
    if jobs:
        name = max(jobs, key=lambda job: job["metadata"]["creationTimestamp"])[
            "metadata"
        ]["name"]
        for container in ("backup", "download", "restore"):
            try:
                output = kube.run("logs", f"job/{name}", "-c", container)
            except ValueError:
                continue
            print(output.decode(), end="")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=(
            "enroll",
            "configure",
            "init-repo",
            "enable",
            "disable",
            "status",
            "verify",
        ),
    )
    parser.add_argument("--ram-root", type=Path, default=Path("/dev/shm"))
    args = parser.parse_args()
    try:
        secrets.harden()
        os.umask(0o077)
        if args.action == "enroll":
            enroll()
            return 0
        kubeconfig = tofu.get_kubeconfig(args.ram_root)
        with tofu.recovery.config.memory_file(kubeconfig) as fd:
            kube = Kubernetes(fd)
            match args.action:
                case "configure":
                    configure(
                        kube,
                        os.environ.get("R2_REPOSITORY", ""),
                        tool("homelab-unwrap"),
                    )
                case "init-repo":
                    wait_for_job(kube, private_job(kube, "init-repo"))
                case "enable":
                    wait_for_job(kube, private_job(kube, "check-repo"))
                    kube.run(
                        "patch",
                        "cronjob",
                        NAME,
                        "--type=merge",
                        "-p",
                        '{"spec":{"suspend":false}}',
                    )
                    print("Backup and sealed restore schedule enabled.", flush=True)
                case "disable":
                    kube.run(
                        "patch",
                        "cronjob",
                        NAME,
                        "--type=merge",
                        "-p",
                        '{"spec":{"suspend":true}}',
                    )
                    print("Backup and sealed restore schedule suspended.", flush=True)
                case "status":
                    show_status(kube)
                case "verify":
                    verify(
                        kube,
                        os.environ.get("RESTORE_SNAPSHOT_ID", ""),
                        tool("homelab-unwrap"),
                    )
                case _:
                    raise ValueError("Unknown OpenBao backup command")
    except (
        OSError,
        ValueError,
        KeyError,
        http.client.HTTPException,
        subprocess.SubprocessError,
        KeyboardInterrupt,
    ) as exc:
        detail = str(exc) if type(exc) is ValueError else type(exc).__name__
        print(f"Trust OpenBao backup operation failed: {detail}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
