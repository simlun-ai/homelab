"""Enroll the Backup Talos identity and install or check the encrypted OS."""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import cast

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trust_talos_config as config
import trust_talos_recovery as recovery
import trust_talos_secrets as secrets

SCOPE = secrets.ROOT / "clusters/backup"
PATCH = SCOPE / "talos/backup-cp1.yaml"
SCHEMATIC = SCOPE / "talos/backup-cp1.schematic.yaml"
RECORD = secrets.ROOT / "secrets/wrapped/backup-talos-bootstrap.json"
KEY_ID = "homelab/v1/backup/talos/bootstrap/r1"
NODE = "10.10.0.15"
ENDPOINT = f"https://{NODE}:6443"


def installer_image() -> str:
    identifier = SCHEMATIC.with_suffix(".id").read_text(encoding="ascii").strip()
    image = SCHEMATIC.with_suffix(".amd64.image").read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[a-f0-9]{64}", identifier) or not re.fullmatch(
        rf"factory\.talos\.dev/metal-installer/{identifier}@sha256:[a-f0-9]{{64}}",
        image,
    ):
        raise secrets.PreflightError(
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
        talos_version=secrets.cluster_version("talos", cluster="backup"),
        kubernetes_version=secrets.cluster_version("kubernetes", cluster="backup"),
        public_args=[
            "--install-image",
            installer_image(),
            "--config-patch-control-plane",
            f"@{PATCH}",
        ],
    )


def maintenance_query(talosctl: str, resource: str) -> bytes:
    return secrets.capture_bundle(
        [talosctl, "get", resource, "--insecure", "--nodes", NODE, "-o", "yaml"],
        timeout=20,
    )


def check_install_target(talosctl: str, machine: bytes) -> None:
    registration = (
        secrets.ROOT / "clusters/trust/tofu-workload/talos-kms.json"
    ).read_bytes()
    nodes: dict[str, str] = json.loads(registration)["clusters"]["backup"]["nodes"]
    observed = recovery.field(
        recovery.field(
            yaml.safe_load(maintenance_query(talosctl, "systeminformation")), "spec"
        ),
        "uuid",
    )
    if not isinstance(observed, str) or nodes.get(observed.lower()) != NODE:
        raise secrets.PreflightError(
            "Maintenance node does not match the Backup KMS registration"
        )

    documents: list[object] = list(yaml.safe_load_all(machine))
    selector = recovery.field(
        recovery.field(
            recovery.field(
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
        raise secrets.PreflightError(
            "Backup RAID selector must name two exact disk links"
        )
    first, second = match.groups()
    first_disks: list[str] = []
    second_disks: list[str] = []
    disks: list[object] = list(yaml.safe_load_all(maintenance_query(talosctl, "disks")))
    for disk in disks:
        spec = recovery.field(disk, "spec")
        links = recovery.field(spec, "symlinks")
        device = recovery.field(spec, "dev_path")
        if not isinstance(links, list) or not isinstance(device, str):
            continue
        if first in links:
            first_disks.append(device)
        if second in links:
            second_disks.append(device)
    if len(first_disks) != 1 or len(second_disks) != 1 or first_disks == second_disks:
        raise secrets.PreflightError(
            "Backup's two selected OS disks were not found uniquely"
        )
    print(f"Verified Backup UUID and both OS disks at {NODE}.", flush=True)


def check_volumes(talosctl: str, bundle: bytes, ram_root: Path) -> bool:
    ca, key = recovery.talos_ca(bundle)
    client = recovery.credentials.issue(
        talosctl, ca, key, ram_root, context="backup", node=NODE
    )
    ready = True
    with config.memory_file(client) as fd:
        for name in ("STATE", "EPHEMERAL"):
            report = secrets.capture_bundle(
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
            spec = recovery.field(yaml.safe_load(report), "spec")
            phase = recovery.field(spec, "phase")
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
        secrets.harden()
        secrets.require_private_repository(record=RECORD)
        talosctl = secrets.executable(args.talosctl, "talosctl")
        hsm_tool = secrets.executable(args.hsm_tool, "homelab-wrap/unwrap")
        with secrets.hsm_progress_terminal() as terminal:
            if args.action == "enroll":
                if os.path.lexists(RECORD):
                    raise secrets.PreflightError(
                        "Backup bootstrap record already exists"
                    )
                stage = "Backup identity generation and wrapping"
                print(
                    "Touch the YubiKey when prompted to enroll the Backup identity.",
                    flush=True,
                )
                secrets.wrap_bundle(
                    secrets.generate(talosctl, cluster="backup"),
                    hsm_tool,
                    record=RECORD,
                    key_id=KEY_ID,
                    stderr=terminal,
                )
                print("Verified encrypted Backup bootstrap record created.")
                return 0
            stage = "Backup identity recovery"
            if args.action == "status":
                with recovery.credentials.ram_directory(args.ram_root):
                    pass
            print(
                "Touch the YubiKey when prompted to recover the Backup identity.",
                flush=True,
            )
            bundle = secrets.recover_bundle(
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
    except secrets.PreflightError as exc:
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
