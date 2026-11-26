"""Rehearse native 24-hour Talos client issuance on verified tmpfs only."""

import argparse
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trust_talos_config as config
from homelab.talos import credentials as common_credentials
from homelab.talos.credentials import (
    interrupted as interrupted,
)
from homelab.talos.credentials import (
    ram_directory as ram_directory,
)
from homelab.talos.credentials import (
    read_file,
    run_native,
)
from homelab.talos.credentials import (
    require_tmpfs as require_tmpfs,
)


def issue(
    talosctl: str,
    ca_crt: bytes,
    ca_key: bytes,
    root: Path,
    *,
    context: str = config.CLUSTER,
    node: str | None = None,
) -> bytes:
    return common_credentials.issue(
        talosctl, ca_crt, ca_key, root, context=context, node=node
    )


def rehearse(talosctl: str, root: Path) -> None:
    print("Generating a disposable CA with native Talos tooling on tmpfs.", flush=True)
    with ram_directory(root) as (path, fd):
        run_native(talosctl, ["gen", "ca", "--organization", "ca"], path, fd)
        ca_crt, ca_key = read_file(path / "ca.crt"), read_file(path / "ca.key")
    print(
        "Issuing a 24-hour administration credential from the supplied CA.", flush=True
    )
    issue(talosctl, ca_crt, ca_key, root)
    print(
        "PASS: issuer signature, client key, os:admin role, client-auth usage and 24-hour expiry."
    )
    print("PASS: native talosconfig assembly and inspection; RAM workspaces removed.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--talosctl", required=True, type=Path)
    parser.add_argument("--ram-root", type=Path, default=Path("/dev/shm"))
    args = parser.parse_args()
    try:
        config.secrets.harden()
        signal.signal(signal.SIGTERM, interrupted)
        signal.signal(signal.SIGHUP, interrupted)
        rehearse(config.secrets.executable(args.talosctl, "talosctl"), args.ram_root)
    except config.secrets.PreflightError as exc:
        print(f"Credential preflight failed: {exc}", file=sys.stderr)
        return 1
    except (Exception, KeyboardInterrupt):
        print(
            "Credential rehearsal failed; details suppressed. Check the last stage and RAM workspace availability.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
