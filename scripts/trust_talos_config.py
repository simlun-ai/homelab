"""Offline disposable Talos generation; no node operations or persistent files."""

import argparse
import fcntl
import json
import os
import subprocess
import sys
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path

# Explicit local module path, including when launched with Python -I.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import trust_talos_secrets as secrets

SCOPE = Path(__file__).resolve().parents[1] / "clusters/trust"
CLUSTER = "trust-rehearsal"
ENDPOINT = "https://trust-rehearsal.invalid:6443"
INSTALL_DISK = "/dev/REHEARSAL-DO-NOT-INSTALL"
# Linux UAPI values; some Python builds omit the symbolic fcntl constants.
F_ADD_SEALS = getattr(fcntl, "F_ADD_SEALS", 1033)
F_GET_SEALS = getattr(fcntl, "F_GET_SEALS", 1034)
SEALS = 0x0001 | 0x0002 | 0x0004 | 0x0008  # SEAL, SHRINK, GROW, WRITE


@contextmanager
def memory_file(content: bytes) -> Generator[int]:
    """Create a private anonymous shmem file, then seal it against modification."""
    fd = os.memfd_create("talos-rehearsal", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        os.fchmod(fd, 0o600)
        remaining = memoryview(content)
        while remaining:
            count = os.write(fd, remaining)
            if count <= 0:
                raise RuntimeError("Cannot fill protected memory descriptor")
            remaining = remaining[count:]
        os.lseek(fd, 0, os.SEEK_SET)
        fcntl.fcntl(fd, F_ADD_SEALS, SEALS)
        if fcntl.fcntl(fd, F_GET_SEALS) & SEALS != SEALS:
            raise RuntimeError("Cannot seal protected memory descriptor")
        yield fd
    finally:
        os.close(fd)


def generate(talosctl: str, bundle: bytes, output_type: str) -> bytes:
    with memory_file(bundle) as fd:
        return secrets.capture_bundle(
            [
                talosctl,
                "gen",
                "config",
                CLUSTER,
                ENDPOINT,
                "--talos-version",
                secrets.cluster_version("talos"),
                "--kubernetes-version",
                secrets.cluster_version("kubernetes"),
                "--with-secrets",
                f"/proc/self/fd/{fd}",
                "--config-patch",
                "@" + str(SCOPE / "talos/rendered/trust-cp1.yaml"),
                "--install-disk",
                INSTALL_DISK,
                "--with-docs=false",
                "--with-examples=false",
                "--output-types",
                output_type,
                "--output",
                "-",
            ],
            timeout=60,
            pass_fds=(fd,),
        )


def validate_machine(talosctl: str, config: bytes) -> None:
    with memory_file(config) as fd:
        subprocess.run(
            [
                talosctl,
                "validate",
                "--config",
                f"/proc/self/fd/{fd}",
                "--mode",
                "metal",
                "--strict",
            ],
            pass_fds=(fd,),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=60,
        )


def validate_client(talosctl: str, config: bytes) -> None:
    with memory_file(config) as fd:
        result = secrets.capture_bundle(
            [
                talosctl,
                "config",
                "info",
                "--talosconfig",
                f"/proc/self/fd/{fd}",
                "--output",
                "json",
            ],
            timeout=60,
            pass_fds=(fd,),
        )
    info: dict[str, object] = json.loads(result)
    if info.get("context") != CLUSTER or info.get("roles") != ["os:admin"]:
        raise ValueError("Unexpected generated client identity or roles")
    expiry = info.get("certNotAfter")
    if not isinstance(expiry, str):
        raise ValueError("Missing client certificate expiry")
    if date.fromisoformat(expiry) <= datetime.now(UTC).date():
        raise ValueError("Generated client certificate is expired")


def rehearse(talosctl: str) -> None:
    print("Checking sealed anonymous memory descriptors.", flush=True)
    try:
        with memory_file(b""):
            pass
    except (AttributeError, OSError, RuntimeError):
        raise secrets.PreflightError("Linux sealed memfd support is required") from None
    print("Generating disposable secrets in memory.", flush=True)
    bundle = secrets.generate(talosctl)
    print(
        "Generating full rehearsal configuration with the committed public patches.",
        flush=True,
    )
    machine = generate(talosctl, bundle, "controlplane")
    validate_machine(talosctl, machine)
    print("PASS: native strict metal-mode validation of generated configuration.")
    try:
        generate(talosctl, b"invalid disposable bundle", "controlplane")
    except RuntimeError:
        pass
    else:
        raise ValueError("Native generation accepted invalid supplied secrets")
    print("PASS: invalid supplied secrets are rejected without implicit regeneration.")
    print(
        "Generating Talos administration credentials twice from the same bundle.",
        flush=True,
    )
    client = generate(talosctl, bundle, "talosconfig")
    validate_client(talosctl, client)
    renewed = generate(talosctl, bundle, "talosconfig")
    validate_client(talosctl, renewed)
    if client == renewed:
        raise ValueError("Expected newly issued administration credentials")
    print("PASS: native Talos administration credential issuance and reissuance.")
    print("PASS: sealed descriptors closed; no named plaintext files created.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--talosctl", type=Path, required=True)
    args = parser.parse_args()
    try:
        secrets.harden()
        rehearse(secrets.executable(args.talosctl, "talosctl"))
    except secrets.PreflightError as exc:
        print(f"Configuration preflight failed: {exc}", file=sys.stderr)
        return 1
    except (Exception, KeyboardInterrupt):
        print(
            "Configuration rehearsal failed; details suppressed. See the last stage above.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
