"""Deterministically assemble public native Talos configuration documents.

This produces a patch bundle, not a complete deployable MachineConfig.
Full generation and validation with secrets will be a separate memory-only step.
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PATCHES = ROOT / "talos" / "patches"
RENDERED = ROOT / "talos" / "rendered" / "trust-cp1.yaml"
LAYERS = ("cluster", "controlplane", "nodes/trust-cp1")
META = re.compile(r"^(apiVersion|kind|name):[ \t]*(.+?)[ \t]*$", re.M)
SENSITIVE = re.compile(
    r"^[ \t]*(?:token|secret|secrets|key|privateKey|crt|cert|certificate|"
    r"clientSecret|bootstrapToken|password|ca)[ \t]*:",
    re.M | re.I,
)


def render() -> bytes:
    documents: list[str] = []
    identities: set[tuple[str, str, str]] = set()
    for layer in LAYERS:
        directory = PATCHES / layer
        if not directory.is_dir():
            if layer == "controlplane":
                continue  # No role-specific patches yet.
            raise ValueError(f"Missing patch directory: {directory}")
        for path in sorted(directory.glob("*.yaml")):
            source = path.read_text(encoding="utf-8")
            if not source.strip() or "\r" in source or not source.endswith("\n"):
                raise ValueError(f"Expected nonempty LF-terminated patch: {path}")
            if re.search(r"(?m)^---(?:[ \t]|$)|^\.\.\.(?:[ \t]|$)", source):
                raise ValueError(f"Use one YAML document per patch file: {path}")
            if SENSITIVE.search(source):
                raise ValueError(f"Potential sensitive field in patch: {path}")
            pairs = META.findall(source)
            metadata = dict(pairs)
            if len(pairs) != len(metadata) or metadata.get("apiVersion") != "v1alpha1":
                raise ValueError(f"Expected one native v1alpha1 document: {path}")
            kind = metadata.get("kind")
            if not kind:
                raise ValueError(f"Missing Talos kind: {path}")
            identity = (metadata["apiVersion"], kind, metadata.get("name", ""))
            if identity in identities:
                raise ValueError(f"Duplicate Talos document {identity}: {path}")
            identities.add(identity)
            documents.append(source.rstrip("\n"))
    if not documents:
        raise ValueError("No Talos patch documents found")
    return ("\n---\n".join(documents) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("render", "check"))
    action = parser.parse_args().action
    try:
        expected = render()
        if action == "check":
            if not RENDERED.is_file() or RENDERED.read_bytes() != expected:
                print("Rendered Trust YAML is stale; run make -C clusters/trust render", file=sys.stderr)
                return 1
            print("Trust rendered YAML matches the patches.")
        else:
            RENDERED.parent.mkdir(parents=True, exist_ok=True)
            RENDERED.write_bytes(expected)
            print(f"Rendered {RENDERED.relative_to(ROOT)}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"Trust rendering failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
