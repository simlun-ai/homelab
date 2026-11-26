"""Enroll the Backup Talos identity and install or check the encrypted OS."""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import cast

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from homelab.talos import authority, bootstrap, config, credentials

ROOT = Path(__file__).resolve().parents[1]
SCOPE = ROOT / "clusters/backup"
PATCH = SCOPE / "talos/backup-cp1.yaml"
SCHEMATIC = SCOPE / "talos/backup-cp1.schematic.yaml"
RECORD = ROOT / "secrets/wrapped/backup-talos-bootstrap.json"
KEY_ID = "homelab/v1/backup/talos/bootstrap/r1"
NODE = "10.10.0.15"
# Verified in Talos maintenance mode and used for the KMS registration.
NODE_UUID = "038e1b94-a0f6-11e4-9c0a-9d5496c01100"
ENDPOINT = f"https://{NODE}:6443"


def installer_image() -> str:
    identifier = SCHEMATIC.with_suffix(".id").read_text(encoding="ascii").strip()
    image = SCHEMATIC.with_suffix(".amd64.image").read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[a-f0-9]{64}", identifier) or not re.fullmatch(
        rf"factory\.talos\.dev/metal-installer/{identifier}@sha256:[a-f0-9]{{64}}",
        image,
    ):
        raise bootstrap.PreflightError(
            "Backup installer pin does not match the schematic"
        )
    return image


def generate(talosctl: str, bundle: bytes) -> bytes:
    return config.generate_machine_config(
        talosctl,
        bundle,
        "controlplane",
        cluster="backup",
        endpoint=ENDPOINT,
        talos_version=bootstrap.cluster_version("talos", SCOPE),
        kubernetes_version=bootstrap.cluster_version("kubernetes", SCOPE),
        public_args=[
            "--install-image",
            installer_image(),
            "--config-patch-control-plane",
            f"@{PATCH}",
        ],
    )


def maintenance_query(talosctl: str, resource: str) -> bytes:
    return bootstrap.capture_bundle(
        [talosctl, "get", resource, "--insecure", "--nodes", NODE, "-o", "yaml"],
        timeout=20,
    )


def check_install_target(talosctl: str, machine: bytes) -> None:
    observed = authority.field(
        authority.field(
            yaml.safe_load(maintenance_query(talosctl, "systeminformation")), "spec"
        ),
        "uuid",
    )
    if not isinstance(observed, str) or observed.lower() != NODE_UUID:
        raise bootstrap.PreflightError(
            "Maintenance node does not match the verified Backup UUID"
        )

    documents: list[object] = list(yaml.safe_load_all(machine))
    selector = authority.field(
        authority.field(
            authority.field(
                next(
                    cast(dict[str, object], doc)
                    for doc in documents
                    if isinstance(doc, dict)
                    and cast(dict[str, object], doc).get("kind") == "RAIDArrayConfig"
                ),
                "provisioning",
            ),
            "volumeSelector",
        ),
        "match",
    )
    member = r'"(/dev/disk/by-id/[^"\s]+)" in disk\.symlinks'
    match = (
        re.fullmatch(rf"{member}\s*\|\|\s*{member}", selector)
        if isinstance(selector, str)
        else None
    )
    if match is None or match[1] == match[2]:
        raise bootstrap.PreflightError(
            "Backup RAID selector must name two exact disk links"
        )
    first, second = match.groups()
    first_disks: list[str] = []
    second_disks: list[str] = []
    disks: list[object] = list(yaml.safe_load_all(maintenance_query(talosctl, "disks")))
    for disk in disks:
        spec = authority.field(disk, "spec")
        links = authority.field(spec, "symlinks")
        device = authority.field(spec, "dev_path")
        if not isinstance(links, list) or not isinstance(device, str):
            continue
        if first in links:
            first_disks.append(device)
        if second in links:
            second_disks.append(device)
    if len(first_disks) != 1 or len(second_disks) != 1 or first_disks == second_disks:
        raise bootstrap.PreflightError(
            "Backup's two selected OS disks were not found uniquely"
        )
    print(f"Verified Backup UUID and both OS disks at {NODE}.", flush=True)


def check_volumes(talosctl: str, bundle: bytes, ram_root: Path) -> bool:
    ca, key = authority.talos_ca(bundle)
    client = credentials.issue(talosctl, ca, key, ram_root, context="backup", node=NODE)
    ready = True
    with config.memory_file(client) as fd:
        for name in ("STATE", "EPHEMERAL"):
            report = bootstrap.capture_bundle(
                [
                    talosctl,
                    "get",
                    "volumestatus",
                    name,
                    "--talosconfig",
                    f"/proc/self/fd/{fd}",
                    "--nodes",
                    NODE,
                    "--endpoints",
                    NODE,
                    "-o",
                    "yaml",
                ],
                timeout=20,
                pass_fds=(fd,),
            )
            spec = authority.field(yaml.safe_load(report), "spec")
            phase = authority.field(spec, "phase")
            provider = (
                cast(dict[str, object], spec).get("encryptionProvider")
                if isinstance(spec, dict)
                else None
            )
            if phase != "ready" or provider != "luks2":
                print(f"{name}: encrypted volume is not ready", file=sys.stderr)
                ready = False
            else:
                print(f"{name}: ready (LUKS2)")
    return ready


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("enroll", "validate", "apply", "status"))
    parser.add_argument("--talosctl", type=Path, required=True)
    parser.add_argument("--hsm-tool", type=Path, required=True)
    parser.add_argument("--ram-root", type=Path, default=Path("/dev/shm"))
    args = parser.parse_args()
    stage = "workstation and wrapped-record preflight"
    try:
        bootstrap.harden()
        bootstrap.require_private_repository(root=ROOT, record=RECORD)
        talosctl = bootstrap.executable(args.talosctl, "talosctl")
        hsm_tool = bootstrap.executable(args.hsm_tool, "homelab-wrap/unwrap")
        with bootstrap.hsm_progress_terminal() as terminal:
            if args.action == "enroll":
                if os.path.lexists(RECORD):
                    raise bootstrap.PreflightError(
                        "Backup bootstrap record already exists"
                    )
                stage = "Backup identity generation and wrapping"
                print(
                    "Touch the YubiKey when prompted to enroll the Backup identity.",
                    flush=True,
                )
                bootstrap.wrap_bundle(
                    bootstrap.generate_secrets(
                        talosctl, bootstrap.cluster_version("talos", SCOPE)
                    ),
                    hsm_tool,
                    record=RECORD,
                    key_id=KEY_ID,
                    stderr=terminal,
                )
                print("Verified encrypted Backup bootstrap record created.")
                return 0
            stage = "Backup identity recovery"
            if args.action == "status":
                with credentials.ram_directory(args.ram_root):
                    pass
            print(
                "Touch the YubiKey when prompted to recover the Backup identity.",
                flush=True,
            )
            bundle = bootstrap.recover_bundle(
                hsm_tool, record=RECORD, key_id=KEY_ID, stderr=terminal
            )
        if args.action == "status":
            stage = "authenticated encrypted volume status"
            return 0 if check_volumes(talosctl, bundle, args.ram_root) else 1
        stage = "in-memory configuration generation and strict validation"
        machine = generate(talosctl, bundle)
        config.validate_machine(talosctl, machine)
        print("PASS: native strict metal-mode validation for Backup.", flush=True)
        if args.action == "apply":
            stage = "maintenance UUID and disk identity preflight"
            check_install_target(talosctl, machine)
            stage = "installation apply. Check the console before retrying"
            config.apply_install(talosctl, machine, node=NODE)
            print(
                "PASS: Talos accepted the configuration. Watch the console for installation."
            )
    except bootstrap.PreflightError as exc:
        print(f"Backup preflight failed: {exc}", file=sys.stderr)
        return 1
    except (Exception, KeyboardInterrupt):
        print(
            f"Backup operation failed during {stage}. Native output suppressed.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
