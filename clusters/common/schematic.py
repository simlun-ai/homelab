"""Prepare pinned Talos Image Factory boot assets."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
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


def read_id(source: Path) -> str:
    identifier = source.with_suffix(".id").read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{64}", identifier):
        raise ValueError("Invalid schematic ID")
    return identifier


def write_installer_image(source: Path, *, arch: str, scope: Path) -> Path:
    identifier = read_id(source)
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


def download_iso(source: Path, *, arch: str, scope: Path) -> Path:
    identifier = read_id(source)
    release = version("talos", scope)
    pin = source.with_suffix(f".{arch}.iso.sha256")
    expected = pin.read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError(f"Invalid ISO SHA-256 in {pin}")
    target = scope / "boot" / f"metal-{arch}.iso"
    if target.is_file() and not target.is_symlink():
        with target.open("rb") as existing:
            if hashlib.file_digest(existing, "sha256").hexdigest() == expected:
                print(f"Verified cached ISO SHA-256 for {target}", flush=True)
                return target

    url = f"https://{FACTORY}/image/{identifier}/{release}/{target.name}"
    curl = shutil.which("curl")
    if curl is None:
        raise ValueError("Install curl on the workstation to download the ISO")
    target.parent.mkdir(exist_ok=True)
    print(f"Downloading {url}", flush=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        subprocess.run(
            [
                curl,
                "--fail",
                "--location",
                "--show-error",
                "--output",
                str(temporary),
                url,
            ],
            check=True,
        )
        with temporary.open("rb") as download:
            if hashlib.file_digest(download, "sha256").hexdigest() != expected:
                raise ValueError(f"ISO SHA-256 mismatch for {url}")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Verified ISO SHA-256 for {target}", flush=True)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--installer-image", action="store_true")
    action.add_argument("--iso", action="store_true")
    parser.add_argument("--arch", choices=("amd64", "arm64"))
    parser.add_argument("--scope", type=Path)
    parser.add_argument("schematic", type=Path)
    args = parser.parse_args()
    if (args.installer_image or args.iso) and (args.arch is None or args.scope is None):
        parser.error("--installer-image and --iso require --arch and --scope")
    try:
        if args.installer_image:
            output = write_installer_image(
                args.schematic, arch=args.arch, scope=args.scope
            )
        elif args.iso:
            download_iso(args.schematic, arch=args.arch, scope=args.scope)
            return 0
        else:
            output = write_id(args.schematic)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Image Factory generation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
