"""Run a Trust OpenTofu root from a verified RAM workspace."""

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import urllib.request
from collections.abc import Generator
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trust_talos_recovery as recovery  # noqa: E402
import trust_tofu_key as tofu_key  # noqa: E402

ROOT = recovery.secrets.ROOT
SCOPE = ROOT / "clusters/trust"
STATE_REPO = ROOT.parent / "homelab-opentofu-state"
NODE = "10.10.0.10"
CLOUDFLARE_RECORD = ROOT / "secrets/wrapped/trust-cert-manager-cloudflare.json"
CLOUDFLARE_KEY_ID = "homelab/v1/trust/cert-manager/dns-api/cloudflare/r1"
OCI_MANIFEST = "application/vnd.oci.image.manifest.v1+json"
HELM_CONFIG = "application/vnd.cncf.helm.config.v1+json"
HELM_CHART = "application/vnd.cncf.helm.chart.content.v1.tar+gzip"
SHA256_DIGEST = r"sha256:[0-9a-f]{64}"
MAX_CHART_BYTES = 4 * 1024 * 1024


def state_path(scope: tofu_key.StateScope) -> Path:
    name = f"trust-{scope.value}.tfstate"
    if STATE_REPO.is_symlink() or not STATE_REPO.is_dir():
        raise recovery.secrets.PreflightError(
            "Initialize ../homelab-opentofu-state first"
        )
    result = subprocess.run(
        ["git", "-C", STATE_REPO, "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode or Path(result.stdout.strip()).resolve() != STATE_REPO:
        raise recovery.secrets.PreflightError(
            "The state checkout must be its own Git root"
        )
    path = STATE_REPO / name
    for candidate in (path, path.with_suffix(".tfstate.backup")):
        if candidate.is_symlink() or (candidate.exists() and not candidate.is_file()):
            raise recovery.secrets.PreflightError(
                "State and backup paths must be regular files"
            )
    if not path.exists():
        tracked = subprocess.run(
            ["git", "-C", STATE_REPO, "ls-files", "--error-unmatch", "--", name],
            capture_output=True,
            check=False,
            timeout=10,
        )
        if tracked.returncode == 0 or path.with_suffix(".tfstate.backup").exists():
            raise recovery.secrets.PreflightError(
                "Restore the missing state before applying"
            )
    return path


def fetch_oci_chart(repository: str, manifest_digest: str) -> bytes:
    location = re.fullmatch(r"oci://([a-z0-9.-]+)/([a-z0-9_./-]+)", repository)
    if not location or not re.fullmatch(SHA256_DIGEST, manifest_digest):
        raise ValueError("Invalid OCI chart pin")
    registry, path = location.groups()
    endpoint = f"https://{registry}/v2/{path}"
    request = urllib.request.Request(
        f"{endpoint}/manifests/{manifest_digest}",
        headers={"Accept": OCI_MANIFEST},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        manifest = response.read(64 * 1024 + 1)
    if f"sha256:{hashlib.sha256(manifest).hexdigest()}" != manifest_digest:
        raise ValueError("OCI chart manifest digest mismatch")

    data: object = json.loads(manifest)
    match data:
        case {
            "schemaVersion": 2,
            "config": {"mediaType": str(media_type)},
        } if media_type == HELM_CONFIG:
            layers = cast(dict[str, object], data).get("layers")
        case _:
            raise ValueError("Expected an OCI Helm chart manifest")
    if not isinstance(layers, list):
        raise ValueError("Expected OCI Helm chart layers")
    charts: list[tuple[str, int]] = []
    for layer in cast(list[object], layers):
        match layer:
            case {
                "mediaType": str(layer_type),
                "digest": str(digest),
                "size": int(size),
            } if layer_type == HELM_CHART:
                charts.append((digest, size))
            case _:
                continue
    if len(charts) != 1:
        raise ValueError("Expected one Helm chart content layer")
    chart_digest, chart_size = charts[0]
    if not (
        re.fullmatch(SHA256_DIGEST, chart_digest) and 0 < chart_size <= MAX_CHART_BYTES
    ):
        raise ValueError("Invalid OCI Helm chart content descriptor")
    with urllib.request.urlopen(
        f"{endpoint}/blobs/{chart_digest}", timeout=30
    ) as response:
        archive = response.read(chart_size + 1)
    if (
        len(archive) != chart_size
        or f"sha256:{hashlib.sha256(archive).hexdigest()}" != chart_digest
    ):
        raise ValueError("OCI Helm chart content digest or size mismatch")
    return archive


def acquire_chart(work: Path, chart: str) -> None:
    pin = json.loads((work / f"{chart}.json").read_text())
    release, repository = (str(pin[k]) for k in ("version", "repository"))
    if not re.fullmatch(r"v?[0-9]+\.[0-9]+\.[0-9]+", release):
        raise ValueError(f"Invalid {chart} chart version")
    name = f"{chart}-{release}.tgz"
    if repository.startswith("oci://"):
        print(f"Fetching digest-pinned {chart} {release} OCI chart.", flush=True)
        archive = fetch_oci_chart(repository, str(pin.get("manifest_digest", "")))
    else:
        checksum = str(pin.get("sha256", ""))
        if not repository.startswith("https://") or not re.fullmatch(
            r"[0-9a-f]{64}", checksum
        ):
            raise ValueError(f"Invalid {chart} chart pin")
        print(f"Fetching checksum-pinned {chart} {release} chart.", flush=True)
        with urllib.request.urlopen(f"{repository}/{name}", timeout=30) as response:
            archive = response.read(MAX_CHART_BYTES + 1)
        if hashlib.sha256(archive).hexdigest() != checksum:
            raise ValueError(f"{chart} chart SHA-256 mismatch")
    (work / name).write_bytes(archive)


def recover_cloudflare_token() -> str:
    secrets = recovery.secrets
    unwrap = secrets.executable(
        Path(sys.executable).with_name("homelab-unwrap"), "homelab-unwrap"
    )
    print("Touch the YubiKey to recover the Trust cert-manager DNS token.", flush=True)
    with secrets.hsm_progress_terminal() as terminal:
        token = secrets.recover_bundle(
            unwrap, record=CLOUDFLARE_RECORD, key_id=CLOUDFLARE_KEY_ID, stderr=terminal
        )
    if not re.fullmatch(rb"[!-~]{1,512}", token):
        raise recovery.secrets.PreflightError(
            "The wrapped cert-manager record must contain only the Cloudflare token"
        )
    return token.decode("ascii")


def get_kubeconfig(ram_root: Path) -> bytes:
    secrets = recovery.secrets
    talosctl = secrets.executable(SCOPE / "bin/talosctl", "talosctl")
    unwrap = secrets.executable(
        Path(sys.executable).with_name("homelab-unwrap"), "homelab-unwrap"
    )
    secrets.require_private_repository()
    print("Touch the YubiKey to recover the Trust Talos identity.", flush=True)
    with secrets.hsm_progress_terminal() as terminal:
        bundle = secrets.recover_bundle(
            unwrap, record=secrets.RECORD, key_id=secrets.KEY_ID, stderr=terminal
        )
    ca, key = recovery.talos_ca(bundle)
    client = recovery.credentials.issue(
        talosctl, ca, key, ram_root, context="trust", node=NODE
    )
    with recovery.config.memory_file(client) as fd:
        return secrets.capture_bundle(
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


@contextmanager
def key_session(address: Path, scope: tofu_key.StateScope) -> Generator[None]:
    """Serve the state key for this invocation in the private RAM directory."""
    unwrap = recovery.secrets.executable(
        Path(sys.executable).with_name("homelab-unwrap"), "homelab-unwrap"
    )
    print(f"Recovering the Trust {scope.value} OpenTofu state key.", flush=True)
    key = tofu_key.recover(unwrap, scope)
    stopped = threading.Event()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(address))
        listener.listen()
        listener.settimeout(0.2)

        def serve() -> None:
            while not stopped.is_set():
                try:
                    peer, _ = listener.accept()
                except TimeoutError:
                    continue
                with peer:
                    peer.settimeout(1)
                    try:
                        peer.sendall(key)
                    except OSError:
                        # A cancelled key-provider invocation can close its connection.
                        continue

        worker = threading.Thread(target=serve)
        worker.start()
        try:
            yield
        finally:
            stopped.set()
            worker.join()


def init_backend(
    tofu: str, work: Path, env: dict[str, str], state: Path | None
) -> None:
    backend = "-backend=false" if state is None else f"-backend-config=path={state}"
    subprocess.run(
        [tofu, "init", "-input=false", "-lockfile=readonly", backend],
        cwd=work,
        env=env,
        check=True,
    )


def recover_state(tofu: str, path: Path, work: Path, env: dict[str, str]) -> None:
    """Recover an emergency snapshot from verified tmpfs into the encrypted backend."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as source:
        recovery.credentials.require_tmpfs(source.fileno())
        info = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o077
        ):
            raise recovery.secrets.PreflightError(
                "Recovery state must be a private operator-owned regular file on tmpfs"
            )
        envelope: object = json.load(source)
        source.seek(0)
        if not isinstance(envelope, dict) or "encrypted_data" not in envelope:
            subprocess.run(
                [tofu, "state", "push", "-"],
                cwd=work,
                env=env,
                stdin=source,
                check=True,
            )
            return

        # state push accepts plaintext. Open the encrypted snapshot through a
        # separate backend and collect state pull's plaintext only in memory.
        snapshot = work / "recovery-source.tfstate"
        with snapshot.open("xb") as destination:
            shutil.copyfileobj(source, destination)
        source_env = {**env, "TF_DATA_DIR": str(work / "recovery-backend")}
        init_backend(tofu, work, source_env, snapshot)
        plaintext = subprocess.run(
            [tofu, "state", "pull"],
            cwd=work,
            env=source_env,
            stdout=subprocess.PIPE,
            check=True,
        ).stdout
        if not plaintext:
            raise ValueError("The recovery source returned no state")
        subprocess.run(
            [tofu, "state", "push", "-"], cwd=work, env=env, input=plaintext, check=True
        )


def run(
    action: str,
    ram_root: Path,
    recovery_file: Path | None = None,
    *,
    scope: tofu_key.StateScope = tofu_key.StateScope.INFRASTRUCTURE,
) -> None:
    tofu = recovery.secrets.executable(SCOPE / "bin/tofu", "tofu")
    state = None if action == "validate" else state_path(scope)
    needs_cluster = action in ("plan", "apply")
    infrastructure = scope is tofu_key.StateScope.INFRASTRUCTURE
    needs_cloudflare_token = needs_cluster and infrastructure
    if state is not None:
        record = scope.record
        recovery.secrets.require_private_repository(record=record)
        if record.is_symlink() or not record.is_file():
            raise recovery.secrets.PreflightError(
                f"Enroll the wrapped Trust {scope.value} OpenTofu key first"
            )

    if needs_cloudflare_token:
        recovery.secrets.require_private_repository(record=CLOUDFLARE_RECORD)
        if CLOUDFLARE_RECORD.is_symlink() or not CLOUDFLARE_RECORD.is_file():
            raise recovery.secrets.PreflightError(
                "Enroll the Trust cert-manager DNS token first"
            )

    config = SCOPE / ("tofu" if infrastructure else "tofu-workload")
    values = (
        SCOPE / "helm/values" / ("infrastructure" if infrastructure else "workloads")
    )
    charts = (
        ("zfs-localpv", "cert-manager", "metallb") if infrastructure else ("openbao",)
    )
    local_charts = (
        ("trust-acme-issuers", "trust-metallb-config") if infrastructure else ()
    )

    provider_cache = SCOPE / "bin/tofu-provider-cache"
    if provider_cache.parent.is_symlink() or provider_cache.is_symlink():
        raise recovery.secrets.PreflightError(
            "The scoped provider cache must not be a symlink"
        )
    provider_cache.mkdir(mode=0o700, exist_ok=True)

    with recovery.credentials.ram_directory(ram_root) as (anchored, _):
        work = Path(os.readlink(anchored))
        for source in config.glob("*.tf"):
            shutil.copyfile(source, work / source.name)
        shutil.copyfile(config / ".terraform.lock.hcl", work / ".terraform.lock.hcl")
        for chart in charts:
            shutil.copyfile(config / f"{chart}.json", work / f"{chart}.json")
            shutil.copyfile(values / f"{chart}.yaml", work / f"{chart}-values.yaml")
            if recovery_file is None:
                acquire_chart(work, chart)
        for chart in local_charts:
            shutil.copytree(SCOPE / "helm/charts" / chart, work / chart)
        # Keep operational files off disk. Only public provider packages use the
        # executable cache because the RAM mount may be noexec.
        for name in ("tmp", "config", "cache", "data"):
            (work / name).mkdir(mode=0o700)
        cli_config = work / "tofu.rc"
        cli_config.touch(mode=0o600)
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("TF_", "TOFU_", "KUBE", "HELM_"))
        }
        address = work / "state-key.sock"
        env.update(
            TF_CLI_CONFIG_FILE=str(cli_config),
            TF_PLUGIN_CACHE_DIR=str(provider_cache),
            TF_WORKSPACE="default",
            TMPDIR=str(work / "tmp"),
            XDG_CONFIG_HOME=str(work / "config"),
            XDG_CACHE_HOME=str(work / "cache"),
            XDG_DATA_HOME=str(work / "data"),
            TF_VAR_state_key_command=json.dumps(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    str(Path(tofu_key.__file__)),
                    "provide",
                    "--scope",
                    scope.value,
                    "--socket",
                    str(address),
                ]
            ),
            TF_VAR_kubeconfig_path=str(work / "kubeconfig"),
        )
        try:
            with key_session(address, scope) if state is not None else nullcontext():
                init_backend(tofu, work, env, state)
                if recovery_file is not None:
                    recover_state(tofu, recovery_file, work, env)
                    print(f"PASS: recovered state persisted to {state}.", flush=True)
                    return
                if needs_cluster:
                    credential = get_kubeconfig(ram_root)
                    with (work / "kubeconfig").open("xb") as destination:
                        destination.write(credential)
                if needs_cloudflare_token:
                    # Keep this variable out of init and state-recovery environments.
                    env["TF_VAR_cert_manager_cloudflare_token"] = (
                        recover_cloudflare_token()
                    )
                subprocess.run([tofu, action], cwd=work, env=env, check=True)
        finally:
            # OpenTofu can emit a state recovery file after a failed write.
            failed_state = work / "errored.tfstate"
            if failed_state.is_file():
                rescue = Path(
                    tempfile.mkdtemp(
                        prefix=f"trust-{config.name}-recovery-", dir=work.parent
                    )
                )
                failed_state.rename(rescue / failed_state.name)
                print(
                    f"State recovery file retained in RAM: {rescue / failed_state.name}",
                    file=sys.stderr,
                )
        if action == "apply":
            print(f"Review and commit the encrypted state in {state}.", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("validate", "plan", "apply", "state-recover")
    )
    parser.add_argument("--ram-root", type=Path, default=Path("/dev/shm"))
    parser.add_argument(
        "--scope",
        type=tofu_key.StateScope,
        choices=tuple(tofu_key.StateScope),
        default=tofu_key.StateScope.INFRASTRUCTURE,
    )
    parser.add_argument("--recovery-file", type=Path)
    args = parser.parse_args()
    if (args.action == "state-recover") != (args.recovery_file is not None):
        parser.error("--recovery-file is required only for state-recover")
    try:
        recovery.secrets.harden()
        os.umask(0o077)
        run(
            args.action,
            args.ram_root,
            args.recovery_file,
            scope=tofu_key.StateScope(args.scope),
        )
    except recovery.secrets.PreflightError as exc:
        print(f"Trust OpenTofu preflight failed: {exc}", file=sys.stderr)
        return 1
    except (
        OSError,
        ValueError,
        RuntimeError,
        subprocess.SubprocessError,
        KeyboardInterrupt,
    ):
        print(
            "Trust OpenTofu operation failed. See the last stage above.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
