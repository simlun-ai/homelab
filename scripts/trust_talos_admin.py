"""Inspect a fresh 24-hour Trust client without exposing or persisting credentials."""

import argparse
import ipaddress
import json
import signal
import sys
from pathlib import Path
from typing import cast

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trust_talos_recovery as recovery

credentials = recovery.credentials
config = recovery.config
secrets = recovery.secrets
CONTEXT = "trust"


def node_address() -> str:
    """Use the committed public node address instead of a second IP inventory."""
    documents: list[object] = list(
        yaml.safe_load_all(
            (config.SCOPE / "talos/rendered/trust-cp1.yaml").read_bytes()
        )
    )
    addresses: list[str] = []
    for value in documents:
        if not isinstance(value, dict):
            continue
        doc = cast(dict[str, object], value)
        if doc.get("kind") != "LinkConfig":
            continue
        entries = doc.get("addresses")
        if not isinstance(entries, list):
            raise ValueError("Expected public node addresses")
        for entry in cast(list[object], entries):
            address = recovery.field(entry, "address")
            if not isinstance(address, str):
                raise ValueError("Expected a node address")
            interface = ipaddress.ip_interface(address)
            if interface.version == 4:
                addresses.append(str(interface.ip))
    if len(addresses) != 1:
        raise ValueError("Expected one unambiguous Trust IPv4 node address")
    return addresses[0]


def inspect(
    talosctl: str,
    unwrap_cli: str,
    root: Path,
    *,
    repo: Path | None = None,
    record: Path | None = None,
    key_id: str = secrets.KEY_ID,
) -> dict[str, object]:
    record = secrets.RECORD if record is None else record
    secrets.require_private_repository(root=repo, record=record)
    # Reject missing records and unusable RAM before asking for YubiKey touch.
    if not record.is_file() or record.is_symlink():
        raise secrets.PreflightError("Existing wrapped bootstrap record is required")
    node = node_address()
    with credentials.ram_directory(root):
        pass
    print(
        "Touch the YubiKey when it flashes to recover the existing authority.",
        flush=True,
    )
    bundle = secrets.recover_bundle(unwrap_cli, record=record, key_id=key_id)
    ca, key = recovery.talos_ca(bundle)
    client = credentials.issue(talosctl, ca, key, root, context=CONTEXT, node=node)
    info = config.validate_client(talosctl, client, CONTEXT)
    if info.get("endpoints") != [node] or info.get("nodes") != [node]:
        raise ValueError("Unexpected Talos administration target")
    # Never print the raw config or arbitrary native output. Only public metadata.
    public = {
        name: info[name]
        for name in (
            "context",
            "endpoints",
            "nodes",
            "roles",
            "certNotBefore",
            "certNotAfter",
        )
        if name in info
    }
    print(json.dumps(public, indent=2), flush=True)
    print("PASS: 24-hour client inspected locally; protected workspaces removed.")
    return public


def rehearse(talosctl: str, wrap_cli: str, unwrap_cli: str, root: Path) -> None:
    with credentials.ram_directory(root):
        pass
    with secrets.rehearsal_record() as record:
        print(
            "Generating a disposable authority for administration rehearsal.",
            flush=True,
        )
        bundle = secrets.generate(talosctl)
        print(
            "Touch the YubiKey when it flashes for wrapping and verification.",
            flush=True,
        )
        secrets.wrap_bundle(
            bundle, wrap_cli, record=record, key_id=secrets.REHEARSAL_KEY_ID
        )
        del bundle
        before = record.read_bytes()
        inspect(
            talosctl,
            unwrap_cli,
            root,
            repo=record.parents[2],
            record=record,
            key_id=secrets.REHEARSAL_KEY_ID,
        )
        if record.read_bytes() != before:
            raise ValueError("Administration changed the authority record")
    print("PASS: disposable administration rehearsal complete; ciphertext removed.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "rehearse"))
    parser.add_argument("--talosctl", type=Path, required=True)
    parser.add_argument("--unwrap", type=Path, required=True)
    parser.add_argument("--wrap", type=Path)
    parser.add_argument("--ram-root", type=Path, default=Path("/dev/shm"))
    args = parser.parse_args()
    try:
        secrets.harden()
        signal.signal(signal.SIGTERM, credentials.interrupted)
        signal.signal(signal.SIGHUP, credentials.interrupted)
        talosctl = secrets.executable(args.talosctl, "talosctl")
        unwrap = secrets.executable(args.unwrap, "homelab-unwrap")
        if args.action == "rehearse":
            if args.wrap is None:
                raise secrets.PreflightError("Rehearsal requires --wrap")
            rehearse(
                talosctl,
                secrets.executable(args.wrap, "homelab-wrap"),
                unwrap,
                args.ram_root,
            )
        else:
            if args.wrap is not None:
                raise secrets.PreflightError("Inspection accepts no wrapping tool")
            inspect(talosctl, unwrap, args.ram_root)
    except secrets.PreflightError as exc:
        print(f"Administration preflight failed: {exc}", file=sys.stderr)
        return 1
    except (Exception, KeyboardInterrupt):
        print(
            "Administration failed; details suppressed. See the last stage above.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
