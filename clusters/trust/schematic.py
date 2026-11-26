"""Generate Image Factory IDs and digest-pinned installer references."""

import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import cast
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tooling import version  # noqa: E402

FACTORY = "factory.talos.dev"
INDEX_TYPES = "application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json"
MANIFEST_TYPES = "application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json"


def write_id(source: Path) -> Path:
    if source.suffix not in (".yaml", ".yml"):
        raise ValueError("Expected a YAML schematic path")
    request = Request(
        f"https://{FACTORY}/schematics",
        data=source.read_bytes(),
        headers={"Content-Type": "application/yaml"},
    )
    with urlopen(request, timeout=60) as response:
        data: object = json.load(response)
    match data:
        case {"id": str(identifier)} if re.fullmatch(r"[0-9a-f]{64}", identifier):
            pass
        case _:
            raise ValueError("Image Factory returned an invalid schematic ID")

    return write_output(source.with_suffix(".id"), identifier)


def write_output(target: Path, value: str) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="ascii", dir=target.parent, delete=False
    ) as handle:
        temp = Path(handle.name)
    try:
        temp.write_text(value + "\n", encoding="ascii")
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    return target


def registry_manifest(repository: str, selector: str, accept: str) -> bytes:
    request = Request(
        f"https://{FACTORY}/v2/{repository}/manifests/{selector}",
        headers={"Accept": accept},
    )
    with urlopen(request, timeout=120) as response:
        return response.read()


def write_installer_image(
    source: Path, *, arch: str = "arm64", scope: Path | None = None
) -> Path:
    identifier = source.with_suffix(".id").read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{64}", identifier):
        raise ValueError("Invalid schematic ID")
    release = version("talos", scope)
    repository = f"metal-installer/{identifier}"
    print(f"Resolving linux/{arch} installer for {release} ({identifier})", flush=True)
    data: object = json.loads(registry_manifest(repository, release, INDEX_TYPES))
    if not isinstance(data, dict):
        raise ValueError("Image Factory did not return an installer index")
    entries = cast(dict[str, object], data).get("manifests")
    if not isinstance(entries, list):
        raise ValueError("Image Factory did not return an installer index")
    digests: list[str] = []
    for manifest in cast(list[object], entries):
        match manifest:
            case {
                "platform": {"os": "linux", "architecture": str(architecture)},
                "digest": str(digest),
            } if architecture == arch:
                digests.append(digest)
            case _:
                continue

    if len(digests) != 1 or not re.fullmatch(r"sha256:[0-9a-f]{64}", digests[0]):
        raise ValueError(f"Expected one valid linux/{arch} manifest digest")
    digest = digests[0]
    manifest = registry_manifest(repository, digest, MANIFEST_TYPES)
    if f"sha256:{hashlib.sha256(manifest).hexdigest()}" != digest:
        raise ValueError(f"linux/{arch} manifest does not match the index digest")
    return write_output(
        source.with_suffix(f".{arch}.image"), f"{FACTORY}/{repository}@{digest}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installer-image", action="store_true")
    parser.add_argument("--arch", choices=("amd64", "arm64"), default="arm64")
    parser.add_argument("--scope", type=Path)
    parser.add_argument("schematic", type=Path)
    args = parser.parse_args()
    try:
        if args.installer_image:
            output = write_installer_image(
                args.schematic, arch=args.arch, scope=args.scope
            )
        else:
            output = write_id(args.schematic)
    except (OSError, ValueError) as exc:
        print(f"Image Factory generation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
