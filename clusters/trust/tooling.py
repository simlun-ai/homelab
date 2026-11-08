"""Acquire and verify public Trust CLI binaries; never handle credentials."""

import argparse
import hashlib
import os
import platform
import re
import sys
import tempfile
import tomllib
import urllib.request
from pathlib import Path

SCOPE = Path(__file__).resolve().parent
PINS = {"talosctl": "talos", "kubectl": "kubectl"}
MAX_DOWNLOAD = 256 * 1024 * 1024


def progress(message: str) -> None:
    print(f"Trust tools: {message}", file=sys.stderr, flush=True)


def architecture() -> str:
    if platform.system() != "Linux":
        raise ValueError("Trust tools currently support Linux only")
    machine = platform.machine()
    aliases = {"x86_64": "amd64", "aarch64": "arm64"}
    if machine not in aliases:
        raise ValueError(f"Unsupported operator architecture: {machine}")
    return aliases[machine]


def version(component: str) -> str:
    """Read an unquoted release pin from the scope's small versions file."""
    progress(f"Reading {component} release pin from {SCOPE / 'versions.yaml'}")
    source = (SCOPE / "versions.yaml").read_text(encoding="utf-8")
    matches = re.findall(
        rf"(?m)^{re.escape(component)}:[ \t]*\n"
        r"[ \t]+version:[ \t]*(v[0-9]+\.[0-9]+\.[0-9]+)[ \t]*$",
        source,
    )
    if len(matches) != 1:
        raise ValueError(f"Expected one release pin for {component} in versions.yaml")
    return matches[0]


def specification(tool: str, arch: str) -> tuple[str, str]:
    progress(f"Reading download URL and SHA-256 for {tool}/{arch}")
    with (SCOPE / "toolchain.toml").open("rb") as source:
        entry = tomllib.load(source)[tool]
    url = entry["url"].format(version=version(PINS[tool]), arch=arch)
    checksum = entry["sha256"][arch]
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError(f"Invalid HTTPS download URL for {tool}")
    if not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-f]{64}", checksum):
        raise ValueError(f"Invalid SHA-256 for {tool}/{arch}")
    return url, checksum


def verified(path: Path, checksum: str, url: str) -> bool:
    progress(f"Checking cached executable {path}")
    if path.is_symlink() or not path.is_file() or not os.access(path, os.X_OK):
        progress("Cache miss: executable missing, symlinked or not executable")
        return False
    receipt = path.with_suffix(".source")
    progress(f"Checking source receipt {receipt}")
    if receipt.is_symlink() or not receipt.is_file():
        progress("Cache miss: source receipt missing or symlinked")
        return False
    if receipt.read_text(encoding="utf-8") != url + "\n":
        progress(f"Cache miss: source receipt does not match {url}")
        return False
    with path.open("rb") as binary:
        progress(f"Verifying cached SHA-256 against {checksum}")
        matches = hashlib.file_digest(binary, "sha256").hexdigest() == checksum
    progress("Cached SHA-256 matches" if matches else "Cache miss: SHA-256 mismatch")
    return matches


def install(tool: str, url: str, checksum: str) -> None:
    directory = SCOPE / "bin"
    if directory.is_symlink():
        raise ValueError("Tool directory must not be a symlink")
    progress(f"Preparing download directory {directory}")
    directory.mkdir(exist_ok=True)
    temporary: Path | None = None
    receipt: Path | None = None
    try:
        progress(f"Creating temporary download file for {tool}")
        with tempfile.NamedTemporaryFile(
            dir=directory, prefix=f".{tool}-", delete=False
        ) as target:
            temporary = Path(target.name)
            digest = hashlib.sha256()
            size = 0
            progress(f"Downloading {tool} from {url} (30s socket timeout)")
            with urllib.request.urlopen(url, timeout=30) as response:
                progress(f"Receiving {tool} bytes (limit {MAX_DOWNLOAD} bytes)")
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_DOWNLOAD:
                        raise ValueError(f"Download too large: {tool}")
                    digest.update(chunk)
                    target.write(chunk)
            progress(
                f"Verifying downloaded {tool}: {size} bytes, expected SHA-256 {checksum}"
            )
            if not size or digest.hexdigest() != checksum:
                raise ValueError(f"SHA-256 verification failed: {tool}")
        progress(f"Writing source receipt for {tool}")
        with tempfile.NamedTemporaryFile(
            dir=directory, prefix=f".{tool}-source-", delete=False
        ) as source:
            receipt = Path(source.name)
            source.write((url + "\n").encode("utf-8"))
        progress(f"Setting executable permissions and installing {directory / tool}")
        temporary.chmod(0o755)
        temporary.replace(directory / tool)
        progress(f"Installing source receipt {directory / (tool + '.source')}")
        receipt.replace(directory / f"{tool}.source")
    except OSError as exc:
        raise OSError(f"{tool} installation from {url} failed: {exc}") from exc
    finally:
        progress(f"Cleaning temporary download files for {tool}")
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if receipt is not None:
            receipt.unlink(missing_ok=True)


def tools(action: str) -> None:
    progress("Detecting operator platform and architecture")
    arch = architecture()
    progress(f"Selected linux/{arch}; action={action}")
    if (SCOPE / "bin").is_symlink():
        raise ValueError("Tool directory must not be a symlink")
    for tool in PINS:
        url, checksum = specification(tool, arch)
        if not verified(SCOPE / "bin" / tool, checksum, url):
            if action == "check":
                raise ValueError(
                    f"Missing or changed {tool}; run make -C clusters/trust tools"
                )
            install(tool, url, checksum)
        print(f"Verified {tool} {version(PINS[tool])} for linux/{arch}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "check"))
    args = parser.parse_args()
    try:
        tools(args.action)
    except (OSError, ValueError, KeyError) as exc:
        print(f"Trust tooling failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
