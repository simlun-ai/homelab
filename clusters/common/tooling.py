"""Acquire and verify public cluster CLI binaries; never handle credentials."""

import argparse
import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import urllib.request
import zipfile
from pathlib import Path

PINS = {"talosctl": "talos", "kubectl": "kubectl", "tofu": "opentofu"}

MAX_DOWNLOAD = 256 * 1024 * 1024


def progress(message: str) -> None:
    print(f"Cluster tools: {message}", file=sys.stderr, flush=True)


def architecture() -> str:
    if platform.system() != "Linux":
        raise ValueError("Cluster tools currently support Linux only")
    machine = platform.machine()
    aliases = {"x86_64": "amd64", "aarch64": "arm64"}
    if machine not in aliases:
        raise ValueError(f"Unsupported operator architecture: {machine}")
    return aliases[machine]


def version(component: str, scope: Path) -> str:
    """Read an unquoted release pin from the scope's small versions file."""
    pins = scope / "versions.yaml"
    progress(f"Reading {component} release pin from {pins}")
    source = pins.read_text(encoding="utf-8")
    matches = re.findall(
        rf"(?m)^{re.escape(component)}:[ \t]*\n"
        r"[ \t]+version:[ \t]*(v[0-9]+\.[0-9]+\.[0-9]+)[ \t]*$",
        source,
    )
    if len(matches) != 1:
        raise ValueError(f"Expected one release pin for {component} in versions.yaml")
    return matches[0]


def specification(tool: str, arch: str, scope: Path) -> tuple[str, str]:
    progress(f"Reading download URL and SHA-256 for {tool}/{arch}")
    with (scope / "toolchain.toml").open("rb") as source:
        entry = tomllib.load(source)[tool]
    release = version(PINS[tool], scope)
    url = entry["url"].format(version=release, release=release[1:], arch=arch)
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


def install(tool: str, url: str, checksum: str, scope: Path) -> None:
    archive = None
    if tool == "tofu":
        with (scope / "toolchain.toml").open("rb") as source:
            archive = tomllib.load(source)["tofu"]["archive_sha256"][architecture()]
        if not isinstance(archive, str) or not re.fullmatch(r"[0-9a-f]{64}", archive):
            raise ValueError("Invalid OpenTofu ZIP SHA-256")
    directory = scope / "bin"
    if directory.is_symlink():
        raise ValueError("Tool directory must not be a symlink")
    progress(f"Preparing download directory {directory}")
    directory.mkdir(exist_ok=True)
    temporary: Path | None = None
    receipt: Path | None = None
    extracted: Path | None = None
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
        expected = archive or checksum
        progress(
            f"Verifying downloaded {tool}: {size} bytes, expected SHA-256 {expected}"
        )
        if not size or digest.hexdigest() != expected:
            raise ValueError(f"SHA-256 verification failed: {tool}")
        executable = temporary
        if archive is not None:
            progress(f"Extracting and verifying {tool} from the checked ZIP")
            with (
                zipfile.ZipFile(temporary) as package,
                package.open(tool) as source,
                tempfile.NamedTemporaryFile(
                    dir=directory, prefix=f".{tool}-", delete=False
                ) as target,
            ):
                extracted = Path(target.name)
                data = source.read(MAX_DOWNLOAD + 1)
                if (
                    len(data) > MAX_DOWNLOAD
                    or hashlib.sha256(data).hexdigest() != checksum
                ):
                    raise ValueError(f"Extracted binary verification failed: {tool}")
                target.write(data)
            executable = extracted
        progress(f"Writing source receipt for {tool}")
        with tempfile.NamedTemporaryFile(
            dir=directory, prefix=f".{tool}-source-", delete=False
        ) as source:
            receipt = Path(source.name)
            source.write((url + "\n").encode("utf-8"))
        progress(f"Setting executable permissions and installing {directory / tool}")
        executable.chmod(0o755)
        executable.replace(directory / tool)
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
        if extracted is not None:
            extracted.unlink(missing_ok=True)


def htpasswd(action: str) -> None:
    """Provision the distro utility used to generate Zot's bcrypt verifier."""
    if shutil.which("htpasswd") is None:
        if action == "check":
            raise ValueError("Missing htpasswd; run make -C clusters/trust tools")
        apt = shutil.which("apt-get")
        pacman = shutil.which("pacman")
        if apt:
            commands = (
                [apt, "update"],
                [apt, "install", "-y", "--no-install-recommends", "apache2-utils"],
            )
        elif pacman:
            commands = ([pacman, "-S", "--needed", "apache"],)
        else:
            raise ValueError(
                "Install the Linux distribution package that provides htpasswd, then rerun make tools"
            )
        prefix: list[str] = []
        if os.geteuid() != 0:
            sudo = shutil.which("sudo")
            if sudo is None:
                raise ValueError(
                    "Installing the htpasswd system package requires root or sudo"
                )
            prefix = [sudo, "--"]
        progress("Installing htpasswd from the workstation package manager")
        for command in commands:
            subprocess.run([*prefix, *command], check=True)
        if shutil.which("htpasswd") is None:
            raise ValueError("htpasswd is unavailable after installation")
    progress("Verified htpasswd is available")


def tools(action: str, selected: tuple[str, ...] | None = None, *, scope: Path) -> None:
    progress("Detecting operator platform and architecture")
    arch = architecture()
    progress(f"Selected linux/{arch}; action={action}")
    if (scope / "bin").is_symlink():
        raise ValueError("Tool directory must not be a symlink")
    for tool in selected or ("talosctl", "kubectl", "htpasswd"):
        if tool == "htpasswd":
            htpasswd(action)
            continue
        url, checksum = specification(tool, arch, scope)
        if not verified(scope / "bin" / tool, checksum, url):
            if action == "check":
                raise ValueError(
                    f"Missing or changed {tool}; run make -C clusters/{scope.name} "
                    + ("tofu-tools" if tool == "tofu" else "tools")
                )
            install(tool, url, checksum, scope)
        print(
            f"Verified {tool} {version(PINS[tool], scope)} for linux/{arch}", flush=True
        )


def main(default_scope: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "check"))
    parser.add_argument("--tool", choices=(*PINS, "htpasswd"))
    parser.add_argument("--scope", type=Path, default=default_scope)
    args = parser.parse_args()
    if args.scope is None:
        parser.error("--scope is required")
    if default_scope is None and args.tool not in PINS:
        parser.error("select a pinned binary with --tool")
    try:
        tools(args.action, (args.tool,) if args.tool else None, scope=args.scope)
    except (
        OSError,
        ValueError,
        KeyError,
        subprocess.CalledProcessError,
        zipfile.BadZipFile,
    ) as exc:
        print(f"Cluster tooling failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
