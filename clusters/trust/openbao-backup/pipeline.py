"""Export, back up, retrieve, and rehearse a Trust OpenBao Raft snapshot."""

import hashlib
import http.client
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import cast

WORK = Path("/work")
BAO_EXEC = "/tools/bao"
RESTIC_EXEC = "/tools/restic"
ISOLATE = str(Path(__file__).with_name("isolate.py"))
SNAPSHOT = WORK / "raft.snap"
METADATA = WORK / "metadata.json"
RECEIPT = WORK / "receipt"
READY = WORK / "ready"
VERIFIED = WORK / "verified"
CREDENTIALS = Path("/credentials")
TOKEN_FILE = Path("/identity/token")
BAO_NAME = "bao.k8s-aux.simlun.se"
BAO_SERVICE = "openbao.openbao.svc"
AUTH = "/v1/auth/trust-backup/login"
RAFT = "/v1/sys/storage/raft/snapshot"
FIXTURE = "/v1/trust-backup-fixture/data/restore"
FIXTURE_VALUE = "trust-openbao-restore-v1"
RESTIC_HOST = "trust-openbao"
RESTIC_TAG = "trust-openbao-raft"
HEX_ID = re.compile(r"[0-9a-f]{64}")


class ProductionConnection(http.client.HTTPSConnection):
    """Route to the in-cluster service and authenticate its public DNS name."""

    def connect(self) -> None:
        connection = socket.create_connection((BAO_SERVICE, 8200), self.timeout)
        try:
            self.sock = ssl.create_default_context().wrap_socket(
                connection, server_hostname=BAO_NAME
            )
        except BaseException:
            connection.close()
            raise


def request_json(
    conn: http.client.HTTPConnection,
    method: str,
    path: str,
    body: Mapping[str, object] | None = None,
    token: str = "",
) -> dict[str, object]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Vault-Token"] = token
    conn.request(method, path, json.dumps(body) if body is not None else None, headers)
    response = conn.getresponse()
    raw = response.read(512 * 1024 + 1)
    if response.status not in (200, 204) or len(raw) > 512 * 1024:
        raise ValueError(
            f"OpenBao request failed ({method} {path}, HTTP {response.status})"
        )
    if not raw:
        return {}
    value: object = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Unexpected OpenBao response")
    return cast(dict[str, object], value)


def file_digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def export_snapshot() -> None:
    limit = int(os.environ["SNAPSHOT_MAX_BYTES"])
    conn = ProductionConnection(BAO_NAME, timeout=45)
    try:
        auth = request_json(
            conn,
            "POST",
            AUTH,
            {"role": "snapshot", "jwt": TOKEN_FILE.read_text().strip()},
        )
        match auth:
            case {"auth": {"client_token": str(token)}}:
                pass
            case _:
                raise ValueError("OpenBao did not issue a backup token")
        state = request_json(conn, "GET", "/v1/sys/seal-status")
        if (
            state.get("sealed") is not False
            or state.get("version") != os.environ["OPENBAO_VERSION"]
        ):
            raise ValueError(
                "Source OpenBao must be unsealed and match the rehearsal version"
            )
        conn.request("GET", RAFT, headers={"X-Vault-Token": token})
        response = conn.getresponse()
        if response.status != 200:
            raise ValueError(f"Raft snapshot export returned HTTP {response.status}")
        size = 0
        with SNAPSHOT.open("wb") as dest:
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise ValueError("Raft snapshot exceeds the job size limit")
                dest.write(chunk)
        if size == 0:
            raise ValueError("OpenBao returned an empty snapshot")
        digest = file_digest(SNAPSHOT)
        METADATA.write_text(
            json.dumps(
                {
                    "sha256": digest,
                    "bytes": size,
                    "openbao_version": os.environ["OPENBAO_VERSION"],
                    "run_id": os.environ["POD_UID"],
                }
            ),
            encoding="utf-8",
        )
        print(f"RAFT SNAPSHOT bytes={size} sha256={digest}", flush=True)
    finally:
        conn.close()


def restic(*args: str, timeout: int = 480) -> bytes:
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(WORK),
        "TMPDIR": str(WORK),
        "RESTIC_REPOSITORY": os.environ["RESTIC_REPOSITORY"],
        "RESTIC_PASSWORD_FILE": str(CREDENTIALS / "password"),
        "AWS_ACCESS_KEY_ID": (CREDENTIALS / "access-key-id").read_text().strip(),
        "AWS_SECRET_ACCESS_KEY": (CREDENTIALS / "secret-access-key")
        .read_text()
        .strip(),
    }
    result = subprocess.run(
        [RESTIC_EXEC, "--no-cache", "-o", "s3.region=auto", *args],
        env=env,
        cwd=WORK,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=timeout,
        check=False,
    )
    if result.returncode:
        raise ValueError(
            f"restic {next(a for a in args if not a.startswith('-'))} exited {result.returncode}"
        )
    return result.stdout


def backup() -> None:
    RECEIPT.unlink(missing_ok=True)
    try:
        export_snapshot()
        output = restic(
            "backup",
            "--json",
            "--host",
            RESTIC_HOST,
            "--tag",
            RESTIC_TAG,
            "--tag",
            os.environ["POD_UID"],
            SNAPSHOT.name,
            METADATA.name,
        )
        summary: object = json.loads(output.splitlines()[-1])
        match summary:
            case {"message_type": "summary", "snapshot_id": str(snapshot_id)} if (
                HEX_ID.fullmatch(snapshot_id)
            ):
                pass
            case _:
                raise ValueError("restic did not return a full snapshot ID")
        RECEIPT.write_text(snapshot_id, encoding="ascii")
        print(f"BACKUP COMPLETE {snapshot_id}", flush=True)
    finally:
        SNAPSHOT.unlink(missing_ok=True)
        METADATA.unlink(missing_ok=True)


def download() -> None:
    snapshot_id = os.environ.get("RESTORE_SNAPSHOT_ID") or RECEIPT.read_text()
    if not HEX_ID.fullmatch(snapshot_id):
        raise ValueError("Restore requires a full restic snapshot ID")
    RECEIPT.write_text(snapshot_id, encoding="ascii")
    # Read-only R2 credentials cannot create restic locks. Schedule retention
    # separately so pruning cannot race this readback.
    restic("--no-lock", "restore", snapshot_id, "--target", str(WORK), "--verify")
    info: object = json.loads(METADATA.read_text())
    match info:
        case {
            "bytes": int(size),
            "sha256": str(digest),
            "openbao_version": str(version),
        }:
            if (
                size <= 0
                or size > int(os.environ["SNAPSHOT_MAX_BYTES"])
                or SNAPSHOT.stat().st_size != size
                or file_digest(SNAPSHOT) != digest
                or version != os.environ["OPENBAO_VERSION"]
            ):
                raise ValueError("Retrieved Raft snapshot does not match its metadata")
        case _:
            raise ValueError("Unexpected backup metadata")
    print(f"R2 READBACK VERIFIED {snapshot_id}", flush=True)


def connect_rehearsal() -> http.client.HTTPConnection:
    return http.client.HTTPConnection("127.0.0.1", 8200, timeout=120)


def wait_status(
    conn: http.client.HTTPConnection, *, initialized: bool, sealed: bool
) -> None:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            status = request_json(conn, "GET", "/v1/sys/seal-status")
        except (ConnectionError, TimeoutError, http.client.RemoteDisconnected):
            conn.close()
        else:
            if (
                status.get("initialized") is initialized
                and status.get("sealed") is sealed
            ):
                return
        time.sleep(1)
    raise ValueError("Rehearsal OpenBao did not reach the expected seal status")


def install_snapshot(conn: http.client.HTTPConnection) -> None:
    init = request_json(
        conn, "PUT", "/v1/sys/init", {"secret_shares": 1, "secret_threshold": 1}
    )
    match init:
        case {"keys_base64": [str(share)], "root_token": str(token)}:
            pass
        case _:
            raise ValueError("Unexpected initialization reply from disposable OpenBao")
    request_json(conn, "PUT", "/v1/sys/unseal", {"key": share})
    with SNAPSHOT.open("rb") as source:
        conn.request(
            "POST",
            f"{RAFT}-force",
            source,
            {
                "X-Vault-Token": token,
                "Content-Length": str(SNAPSHOT.stat().st_size),
                "Content-Type": "application/octet-stream",
            },
        )
        response = conn.getresponse()
        response.read(512 * 1024)
        if response.status not in (200, 204):
            raise ValueError(
                f"Disposable OpenBao declined the restore (HTTP {response.status})"
            )
    wait_status(conn, initialized=True, sealed=True)


def restore(*, hold: bool) -> None:
    READY.unlink(missing_ok=True)
    VERIFIED.unlink(missing_ok=True)
    raft_data = WORK / "rehearsal-raft"
    raft_data.mkdir(mode=0o700, exist_ok=True)
    if any(raft_data.iterdir()):
        raise ValueError("Rehearsal Raft directory is not empty")
    conf = WORK / "rehearsal.hcl"
    conf.write_text(
        'api_addr = "http://127.0.0.1:8200"\n'
        'cluster_addr = "https://127.0.0.1:8201"\n'
        'listener "tcp" {\n address = "127.0.0.1:8200"\n tls_disable = true\n}\n'
        f'storage "raft" {{\n path = "{raft_data}"\n}}\n',
        encoding="utf-8",
    )
    with subprocess.Popen(
        [sys.executable, "-I", "-B", ISOLATE, BAO_EXEC, "server", "-config", str(conf)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "TMPDIR": str(WORK), "HOME": str(WORK)},
    ) as proc:
        conn = connect_rehearsal()
        try:
            wait_status(conn, initialized=False, sealed=True)
            install_snapshot(conn)
            SNAPSHOT.unlink()
            print(f"RESTORE APPLIED SEALED {RECEIPT.read_text()}", flush=True)
            if hold:
                READY.touch()
                deadline = time.monotonic() + 600
                while not VERIFIED.exists() and time.monotonic() < deadline:
                    time.sleep(1)
                if not VERIFIED.exists():
                    raise ValueError("Timed out waiting for operator verification")
                print(f"RESTORE FIXTURE VERIFIED {RECEIPT.read_text()}", flush=True)
        finally:
            conn.close()
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()


def verify_fixture() -> None:
    if not READY.is_file() or VERIFIED.exists():
        raise ValueError("Disposable restore is not awaiting verification")
    args: object = json.loads(sys.stdin.buffer.read(8192))
    match args:
        case {"share": str(share), "token": str(token)}:
            pass
        case _:
            raise ValueError("Missing restore verification credentials")
    conn = connect_rehearsal()
    try:
        status = request_json(conn, "GET", "/v1/sys/seal-status")
        if status.get("sealed") is True:
            request_json(conn, "PUT", "/v1/sys/unseal", {"key": share})
        wait_status(conn, initialized=True, sealed=False)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            try:
                data = request_json(conn, "GET", FIXTURE, token=token)
            except ValueError:
                time.sleep(2)
                continue
            match data:
                case {"data": {"data": {"value": str(value)}}} if (
                    value == FIXTURE_VALUE
                ):
                    VERIFIED.touch()
                    print("PASS: restored OpenBao fixture matched.", flush=True)
                    return
                case _:
                    raise ValueError("Restored OpenBao fixture did not match")
        raise ValueError("Could not read fixture from restored OpenBao")
    finally:
        conn.close()


def main() -> int:
    os.umask(0o077)
    started = time.monotonic()
    try:
        match sys.argv[1]:
            case "init-repo":
                restic("init")
                print("RESTIC REPOSITORY INITIALIZED", flush=True)
            case "check-repo":
                restic("cat", "config")
                print("RESTIC REPOSITORY ACCESS VERIFIED", flush=True)
            case "backup":
                backup()
            case "download":
                download()
            case "restore":
                restore(hold=False)
            case "restore-hold":
                restore(hold=True)
            case "verify":
                verify_fixture()
            case _:
                raise ValueError("Unknown backup phase")
    except (
        OSError,
        ValueError,
        http.client.HTTPException,
        subprocess.SubprocessError,
    ) as exc:
        # Tracebacks and backend stderr can contain credentials or server output.
        detail = str(exc) if type(exc) is ValueError else type(exc).__name__
        print(f"Trust OpenBao {sys.argv[1]} failed: {detail}", file=sys.stderr)
        return 1
    stats = f"{sys.argv[1]} duration_seconds={time.monotonic() - started:.1f}"
    try:
        peak = Path("/sys/fs/cgroup/memory.peak").read_text().strip()
        if peak.isdecimal():
            stats += f" cgroup_memory_peak_bytes={peak}"
    except OSError:
        pass
    print(stats, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
