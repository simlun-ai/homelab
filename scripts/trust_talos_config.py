"""Assemble Trust Talos configurations in memory and optionally install trust-cp1."""

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

# Explicit local module path, including when launched with Python -I.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import trust_talos_secrets as secrets
from homelab.talos import config as common_config
from homelab.talos.config import (
    memory_file as memory_file,
)
from homelab.talos.config import (
    validate_machine as validate_machine,
)
from homelab.trust_kms import registration

SCOPE = Path(__file__).resolve().parents[1] / "clusters/trust"
CLUSTER = "trust-rehearsal"
ENDPOINT = "https://trust-rehearsal.invalid:6443"
INSTALL_ENDPOINT = "https://trust-api.k8s-aux.lundmark.internal:6443"
INSTALL_NODE = "10.10.0.10"
RAID_PATCH = SCOPE / "talos/experiments/trust-cp1-raid1.yaml"


def generate(
    talosctl: str, bundle: bytes, output_type: str, *, install: bool = False
) -> bytes:
    patches = [
        "--config-patch-control-plane",
        "@" + str(SCOPE / "talos/rendered/trust-cp1.yaml"),
    ]
    if install:
        patches.extend(["--config-patch-control-plane", "@" + str(RAID_PATCH)])
    return common_config.generate_machine_config(
        talosctl,
        bundle,
        output_type,
        cluster="trust" if install else CLUSTER,
        endpoint=INSTALL_ENDPOINT if install else ENDPOINT,
        talos_version=secrets.cluster_version("talos"),
        kubernetes_version=secrets.cluster_version("kubernetes"),
        public_args=patches,
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
    common_config.apply_install(talosctl, config, node=INSTALL_NODE)


def validate_client(
    talosctl: str, config: bytes, expected_context: str = CLUSTER
) -> dict[str, object]:
    return common_config.validate_client(talosctl, config, expected_context)


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
