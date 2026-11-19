"""Assemble Trust Talos configurations in memory and optionally install trust-cp1."""

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

import yaml

# Explicit local module path, including when launched with Python -I.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import trust_talos_secrets as secrets
from homelab.trust_kms import registration

SCOPE = Path(__file__).resolve().parents[1] / "clusters/trust"
CLUSTER = "trust-rehearsal"
ENDPOINT = "https://trust-rehearsal.invalid:6443"
INSTALL_ENDPOINT = "https://trust-api.k8s-aux.lundmark.internal:6443"
INSTALL_NODE = "10.10.0.10"
RAID_PATCH = SCOPE / "talos/experiments/trust-cp1-raid1.yaml"
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


def generate(
    talosctl: str, bundle: bytes, output_type: str, *, install: bool = False
) -> bytes:
    patches = [
        "--config-patch-control-plane",
        "@" + str(SCOPE / "talos/rendered/trust-cp1.yaml"),
    ]
    if install:
        patches.extend(["--config-patch-control-plane", "@" + str(RAID_PATCH)])
    with memory_file(bundle) as fd:
        return secrets.capture_bundle(
            [
                talosctl,
                "gen",
                "config",
                "trust" if install else CLUSTER,
                INSTALL_ENDPOINT if install else ENDPOINT,
                "--talos-version",
                secrets.cluster_version("talos"),
                "--kubernetes-version",
                secrets.cluster_version("kubernetes"),
                "--with-secrets",
                f"/proc/self/fd/{fd}",
                *patches,
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


def check_install_node(talosctl: str) -> None:
    report = secrets.capture_bundle(
        [
            talosctl,
            "get",
            "systeminformation",
            "--insecure",
            "--nodes",
            INSTALL_NODE,
            "-o",
            "yaml",
        ],
        timeout=20,
    )
    if yaml.safe_load(report)["spec"]["uuid"].lower() != registration.NODE:
        raise secrets.PreflightError(
            "Maintenance node does not match the registered trust-cp1 UUID"
        )


def apply_install(talosctl: str, config: bytes) -> None:
    with memory_file(config) as fd:
        subprocess.run(
            [
                talosctl,
                "apply-config",
                "--insecure",
                "--nodes",
                INSTALL_NODE,
                "--file",
                f"/proc/self/fd/{fd}",
            ],
            pass_fds=(fd,),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=60,
        )


def validate_client(
    talosctl: str, config: bytes, expected_context: str = CLUSTER
) -> dict[str, object]:
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
    if info.get("context") != expected_context or info.get("roles") != ["os:admin"]:
        raise ValueError("Unexpected generated client identity or roles")
    expiry = info.get("certNotAfter")
    if not isinstance(expiry, str):
        raise ValueError("Missing client certificate expiry")
    if date.fromisoformat(expiry) <= datetime.now(UTC).date():
        raise ValueError("Generated client certificate is expired")
    return info


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
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--validate-install", action="store_true")
    actions.add_argument("--apply-install", action="store_true")
    parser.add_argument("--unwrap", type=Path)
    args = parser.parse_args()
    if (args.validate_install or args.apply_install) != (args.unwrap is not None):
        parser.error("--unwrap is required with either install action")
    try:
        secrets.harden()
        talosctl = secrets.executable(args.talosctl, "talosctl")
        if args.unwrap is None:
            rehearse(talosctl)
        else:
            unwrap = secrets.executable(args.unwrap, "homelab-unwrap")
            secrets.require_private_repository()
            if args.apply_install:
                print(
                    f"Checking trust-cp1 in maintenance mode at {INSTALL_NODE}.",
                    flush=True,
                )
                check_install_node(talosctl)
            print(
                "Touch the YubiKey to recover the existing Trust bootstrap identity.",
                flush=True,
            )
            bundle = secrets.recover_bundle(
                unwrap, record=secrets.RECORD, key_id=secrets.KEY_ID
            )
            print(
                "Validating the full Trust install configuration in memory.", flush=True
            )
            machine = generate(talosctl, bundle, "controlplane", install=True)
            validate_machine(talosctl, machine)
            print(
                "PASS: full Trust install configuration passed strict metal validation."
            )
            if args.apply_install:
                print(
                    "Sending the install config to trust-cp1; watch the Pi console.",
                    flush=True,
                )
                try:
                    apply_install(talosctl, machine)
                except (OSError, subprocess.SubprocessError, KeyboardInterrupt):
                    print(
                        "Install apply was not acknowledged. Check the Pi console before retrying.",
                        file=sys.stderr,
                    )
                    return 1
                print(
                    "PASS: Talos accepted the install configuration. Check the console for installation progress."
                )

    except secrets.PreflightError as exc:
        print(f"Configuration preflight failed: {exc}", file=sys.stderr)
        return 1
    except (Exception, KeyboardInterrupt):
        print(
            "Configuration operation failed; details suppressed. See the last stage above.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
