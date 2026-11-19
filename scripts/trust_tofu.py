"""Run the Trust OpenTofu root from a verified RAM workspace."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trust_talos_recovery as recovery  # noqa: E402
import trust_tofu_key as tofu_key  # noqa: E402

ROOT = recovery.secrets.ROOT
SCOPE = ROOT / "clusters/trust"
CONFIG = SCOPE / "tofu"
STATE_NAME = "trust-infrastructure.tfstate"
STATE_REPO = ROOT.parent / "homelab-opentofu-state"
NODE = "10.10.0.10"


def state_path() -> Path:
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
    path = STATE_REPO / STATE_NAME
    for candidate in (path, path.with_suffix(".tfstate.backup")):
        if candidate.is_symlink() or (candidate.exists() and not candidate.is_file()):
            raise recovery.secrets.PreflightError(
                "State and backup paths must be regular files"
            )
    if not path.exists():
        tracked = subprocess.run(
            ["git", "-C", STATE_REPO, "ls-files", "--error-unmatch", "--", STATE_NAME],
            capture_output=True,
            check=False,
            timeout=10,
        )
        if tracked.returncode == 0 or path.with_suffix(".tfstate.backup").exists():
            raise recovery.secrets.PreflightError(
                "Restore the missing state before applying"
            )
    return path


def acquire_chart(work: Path) -> None:
    pin = json.loads((CONFIG / "zfs-localpv.json").read_text())
    release, repository, checksum = (
        str(pin[k]) for k in ("version", "repository", "sha256")
    )
    if (
        not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", release)
        or not repository.startswith("https://")
        or not re.fullmatch(r"[0-9a-f]{64}", checksum)
    ):
        raise ValueError("Invalid LocalPV chart pin")
    name = f"zfs-localpv-{release}.tgz"
    print(f"Fetching checksum-pinned ZFS LocalPV {release} chart.", flush=True)
    with urllib.request.urlopen(f"{repository}/{name}", timeout=30) as response:
        archive = response.read(4 * 1024 * 1024 + 1)
    if hashlib.sha256(archive).hexdigest() != checksum:
        raise ValueError("ZFS LocalPV chart SHA-256 mismatch")
    (work / name).write_bytes(archive)


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


def run(action: str, ram_root: Path) -> None:
    tofu = recovery.secrets.executable(SCOPE / "bin/tofu", "tofu")
    state = None if action == "validate" else state_path()
    if state is not None:
        recovery.secrets.require_private_repository(record=tofu_key.RECORD)
        if tofu_key.RECORD.is_symlink() or not tofu_key.RECORD.is_file():
            raise recovery.secrets.PreflightError(
                "Enroll the wrapped OpenTofu key first"
            )

    provider_cache = SCOPE / "bin/tofu-provider-cache"
    if provider_cache.parent.is_symlink() or provider_cache.is_symlink():
        raise recovery.secrets.PreflightError(
            "The scoped provider cache must not be a symlink"
        )
    provider_cache.mkdir(mode=0o700, exist_ok=True)

    with recovery.credentials.ram_directory(ram_root) as (anchored, _):
        work = Path(os.readlink(anchored))
        for source in CONFIG.glob("*.tf"):
            shutil.copyfile(source, work / source.name)
        for name in (".terraform.lock.hcl", "zfs-localpv.json"):
            shutil.copyfile(CONFIG / name, work / name)
        shutil.copyfile(
            SCOPE / "helm/values/infrastructure/zfs-localpv.yaml",
            work / "zfs-localpv-values.yaml",
        )
        acquire_chart(work)
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
        env.update(
            TF_CLI_CONFIG_FILE=str(cli_config),
            TF_PLUGIN_CACHE_DIR=str(provider_cache),
            TF_WORKSPACE="default",
            TMPDIR=str(work / "tmp"),
            XDG_CONFIG_HOME=str(work / "config"),
            XDG_CACHE_HOME=str(work / "cache"),
            XDG_DATA_HOME=str(work / "data"),
            TF_VAR_state_key_command=json.dumps(
                [sys.executable, "-I", "-B", str(Path(tofu_key.__file__)), "provide"]
            ),
            TF_VAR_kubeconfig_path=str(work / "kubeconfig"),
        )
        backend = "-backend=false" if state is None else f"-backend-config=path={state}"
        if state is not None:
            print(
                "Touch the YubiKey when it flashes for OpenTofu state encryption.",
                flush=True,
            )
        subprocess.run(
            [tofu, "init", "-input=false", "-lockfile=readonly", backend],
            cwd=work,
            env=env,
            check=True,
        )
        if state is not None:
            credential = get_kubeconfig(ram_root)
            with (work / "kubeconfig").open("xb") as destination:
                os.fchmod(destination.fileno(), 0o600)
                destination.write(credential)
            print(
                "Touch the YubiKey when it flashes for OpenTofu state encryption.",
                flush=True,
            )
        try:
            subprocess.run([tofu, action], cwd=work, env=env, check=True)
        finally:
            # OpenTofu can emit a state recovery file after a failed write.
            failed_state = work / "errored.tfstate"
            if failed_state.is_file():
                rescue = Path(
                    tempfile.mkdtemp(prefix="trust-tofu-recovery-", dir=work.parent)
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
    parser.add_argument("action", choices=("validate", "plan", "apply"))
    parser.add_argument("--ram-root", type=Path, default=Path("/dev/shm"))
    args = parser.parse_args()
    try:
        recovery.secrets.harden()
        os.umask(0o077)
        run(args.action, args.ram_root)
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
