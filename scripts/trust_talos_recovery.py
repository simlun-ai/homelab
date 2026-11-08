"""Rehearse wrapped Trust recovery without production identities or node operations."""

import argparse
import base64
import hashlib
import hmac
import signal
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trust_talos_credentials as credentials

config = credentials.config
secrets = config.secrets


def field(value: object, name: str) -> object:
    if not isinstance(value, dict):
        raise ValueError("Expected YAML mapping")
    return cast(dict[str, object], value)[name]


def decode(value: object) -> bytes:
    if not isinstance(value, str):
        raise ValueError("Expected encoded credential field")
    decoded = base64.b64decode(value, validate=True)
    if not 0 < len(decoded) <= secrets.MAX_SECRETS:
        raise ValueError("Invalid credential field size")
    return decoded


def load(content: bytes) -> object:
    if not 0 < len(content) <= secrets.MAX_SECRETS:
        raise ValueError("Invalid YAML input size")
    return yaml.safe_load(content)


def talos_ca(bundle: bytes) -> tuple[bytes, bytes]:
    """Read the existing OS authority; missing fields must never regenerate it."""
    authority = field(field(load(bundle), "certs"), "os")
    return decode(field(authority, "crt")), decode(field(authority, "key"))


def client_material(client: bytes) -> tuple[bytes, bytes, bytes]:
    context = field(field(load(client), "contexts"), config.CLUSTER)
    return (
        decode(field(context, "ca")),
        decode(field(context, "crt")),
        decode(field(context, "key")),
    )


def prepare(talosctl: str, bundle: bytes, root: Path) -> bytes:
    ca_crt, ca_key = talos_ca(bundle)
    print("Generating and validating configuration from recovered secrets.", flush=True)
    machine = config.generate(talosctl, bundle, "controlplane")
    config.validate_machine(talosctl, machine)
    # Native generation can emit additional Talos documents. Read only the
    # validated v1alpha1 machine document when checking the issuing authority.
    documents: list[object] = list(yaml.safe_load_all(machine))
    machines = [
        cast(dict[str, object], doc)
        for doc in documents
        if isinstance(doc, dict)
        and cast(dict[str, object], doc).get("version") == "v1alpha1"
    ]
    if len(machines) != 1:
        raise ValueError("Expected one machine configuration")
    machine_ca = field(field(machines[0], "machine"), "ca")
    if not hmac.compare_digest(decode(field(machine_ca, "crt")), ca_crt):
        raise ValueError("Generated machine has a different Talos authority")
    print("PASS: native strict metal validation and recovered machine authority.")
    client = credentials.issue(talosctl, ca_crt, ca_key, root)
    if not hmac.compare_digest(client_material(client)[0], ca_crt):
        raise ValueError("Client configuration has a different Talos authority")
    return client


def exercise(talosctl: str, root: Path, recover: Callable[[], bytes]) -> None:
    bundle = recover()
    digest = hashlib.sha256(bundle).digest()
    first = client_material(prepare(talosctl, bundle, root))
    del bundle
    print("Recovering the same wrapped bundle for fresh credentials.", flush=True)
    bundle = recover()
    if not hmac.compare_digest(hashlib.sha256(bundle).digest(), digest):
        raise ValueError("Repeated recovery changed the bootstrap bundle")
    second = client_material(prepare(talosctl, bundle, root))
    if not hmac.compare_digest(first[0], second[0]):
        raise ValueError("Reissuance changed the Talos authority")
    if hmac.compare_digest(first[1], second[1]) or hmac.compare_digest(
        first[2], second[2]
    ):
        raise ValueError("Reissuance reused client certificate or key")
    print("PASS: fresh 24-hour clients from repeated recovery of the same authority.")


def rehearse(talosctl: str, wrap_cli: str, unwrap_cli: str, root: Path) -> None:
    # Fail before asking for token touches if the protected workspace is unavailable.
    with credentials.ram_directory(root):
        pass
    with secrets.rehearsal_record() as record:
        plaintext = secrets.generate(talosctl)
        digest = hashlib.sha256(plaintext).digest()
        print(
            "Touch the YubiKey when it flashes for wrapping and verification.",
            flush=True,
        )
        secrets.wrap_bundle(
            plaintext, wrap_cli, record=record, key_id=secrets.REHEARSAL_KEY_ID
        )
        del plaintext
        encoded = record.read_bytes()

        def recover() -> bytes:
            print("Touch the YubiKey when it flashes for recovery.", flush=True)
            recovered = secrets.recover_bundle(
                unwrap_cli, record=record, key_id=secrets.REHEARSAL_KEY_ID
            )
            if not hmac.compare_digest(hashlib.sha256(recovered).digest(), digest):
                raise ValueError("Recovered bundle differs from wrapped input")
            return recovered

        exercise(talosctl, root, recover)
        if record.read_bytes() != encoded:
            raise ValueError("Recovery modified the wrapped record")
    print("PASS: temporary ciphertext repository and RAM workspaces removed.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--talosctl", type=Path, required=True)
    parser.add_argument("--wrap", type=Path, required=True)
    parser.add_argument("--unwrap", type=Path, required=True)
    parser.add_argument("--ram-root", type=Path, default=Path("/dev/shm"))
    args = parser.parse_args()
    try:
        secrets.harden()
        signal.signal(signal.SIGTERM, credentials.interrupted)
        signal.signal(signal.SIGHUP, credentials.interrupted)
        rehearse(
            secrets.executable(args.talosctl, "talosctl"),
            secrets.executable(args.wrap, "homelab-wrap"),
            secrets.executable(args.unwrap, "homelab-unwrap"),
            args.ram_root,
        )
    except secrets.PreflightError as exc:
        print(f"Recovery preflight failed: {exc}", file=sys.stderr)
        return 1
    except (Exception, KeyboardInterrupt):
        print(
            "Recovery rehearsal failed; details suppressed. See the last stage above.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
