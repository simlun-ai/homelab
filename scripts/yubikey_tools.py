"""Prepare/install public offline tooling. Never accepts secret material."""

import argparse
import email
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import sysconfig
import venv
import zipfile

ROOT = Path(__file__).resolve().parent.parent
SCOPE = ROOT / "support" / "yubikey"
PIN_FILE = SCOPE / "toolchain.yaml"  # JSON is a YAML subset; no bootstrap parser dependency.


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime():
    if sys.platform != "linux" or platform.python_implementation() != "CPython" or not (3, 11) <= sys.version_info[:2] < (3, 15):
        raise RuntimeError("Requires Linux and CPython 3.11 through 3.14")
    os_release = platform.freedesktop_os_release()
    return {"python": platform.python_version(), "implementation": "CPython",
            "machine": platform.machine(), "abi": sysconfig.get_config_var("SOABI"),
            "os": os_release.get("ID"), "release": os_release.get("VERSION_ID")}


def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def read_bundle(directory):
    manifest = json.loads((directory / "bundle.json").read_text())
    if manifest["format"] != "homelab-yubikey-bundle-v1" or manifest["runtime"] != runtime():
        raise RuntimeError("Bundle needs the same distro/release, architecture, ABI, and exact Python version")
    if manifest["toolchain_sha256"] != digest(PIN_FILE):
        raise RuntimeError("Bundle does not match the scope's toolchain pins")
    pins = json.loads(PIN_FILE.read_text())["packages"]
    packages = manifest["packages"]
    for name, version in pins.items():
        if packages.get(normalize(name)) != version:
            raise RuntimeError("Bundle package pins do not match")
    return manifest


def prepare():
    fingerprint = runtime()
    wheelhouse = SCOPE / "wheelhouse"
    if wheelhouse.exists() or (SCOPE / "bundle.json").exists():
        raise RuntimeError("Use a fresh preparation checkout; a bundle already exists")
    wheelhouse.mkdir(parents=True)
    pins = json.loads(PIN_FILE.read_text())["packages"]
    build_tmp = SCOPE / ".build"
    build_tmp.mkdir(exist_ok=True)
    build_env = dict(os.environ, TMPDIR=str(build_tmp), PIP_DISABLE_PIP_VERSION_CHECK="1")
    subprocess.run([sys.executable, "-m", "pip", "wheel", "--wheel-dir", str(wheelhouse),
                    *(f"{name}=={version}" for name, version in pins.items())], check=True, env=build_env)
    packages, files, locked = {}, {}, []
    for path in sorted(wheelhouse.glob("*.whl")):
        with zipfile.ZipFile(path) as archive:
            members = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
            if len(members) != 1:
                raise RuntimeError("Invalid wheel metadata")
            metadata = email.message_from_bytes(archive.read(members[0]))
        name, version = normalize(metadata["Name"]), metadata["Version"]
        if name in packages:
            raise RuntimeError("Multiple wheels for one package")
        packages[name] = version
        files[path.name] = digest(path)
        locked.append(f"{name}=={version} --hash=sha256:{files[path.name]}")
    lock = SCOPE / "requirements.lock"
    lock.write_text("\n".join(sorted(locked)) + "\n")
    manifest = {"format": "homelab-yubikey-bundle-v1", "runtime": fingerprint,
                "toolchain_sha256": digest(PIN_FILE), "lock_sha256": digest(lock),
                "packages": packages, "wheels": files}
    destination = SCOPE / "bundle.json"
    destination.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    read_bundle(SCOPE)
    print(f"Bundle prepared. Record this SHA-256 separately: {digest(destination)}")


def install(directory):
    directory = directory.resolve()
    manifest = read_bundle(directory)
    if digest(directory / "requirements.lock") != manifest["lock_sha256"]:
        raise RuntimeError("Lock-file checksum mismatch")
    for name, checksum in manifest["wheels"].items():
        if Path(name).name != name or not name.endswith(".whl"):
            raise RuntimeError("Invalid wheel filename")
        if digest(directory / "wheelhouse" / name) != checksum:
            raise RuntimeError("Wheel checksum mismatch")
    actual = {p.name for p in (directory / "wheelhouse").iterdir()}
    if actual != set(manifest["wheels"]):
        raise RuntimeError("Unexpected or missing wheelhouse files")
    environment = SCOPE / ".venv"
    if environment.exists() or (SCOPE / "bin").exists():
        raise RuntimeError("Scope environment already exists; inspect it before rebuilding")
    venv.EnvBuilder(with_pip=True, system_site_packages=False).create(environment)
    python = environment / "bin" / "python"
    subprocess.run([str(python), "-m", "pip", "install", "--no-index", "--no-deps",
                    "--require-hashes", "--find-links", str(directory / "wheelhouse"),
                    "-r", str(directory / "requirements.lock")], check=True)
    subprocess.run([str(python), "-m", "pip", "check"], check=True)
    (SCOPE / "bin").mkdir()
    launcher = SCOPE / "bin" / "python"
    launcher.write_text('#!/bin/sh\nexec "$(dirname -- "$0")/../.venv/bin/python" "$@"\n')
    launcher.chmod(0o755)
    shutil.copyfile(directory / "bundle.json", SCOPE / "bin" / "bundle.json")
    subprocess.run([str(launcher), "-I", "-B", str(Path(__file__).resolve()), "check"], check=True)


def check_environment():
    if Path(sys.prefix).resolve() != (SCOPE / ".venv").resolve():
        raise RuntimeError("Use support/yubikey/bin/python; global tools are not accepted")
    manifest = read_bundle(SCOPE / "bin")
    for name, version in manifest["packages"].items():
        if importlib.metadata.version(name) != version:
            raise RuntimeError("Installed package differs from the offline bundle")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "install", "check"))
    parser.add_argument("--bundle", type=Path, default=SCOPE)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "install":
        install(args.bundle)
    else:
        manifest = check_environment()
        print("Scope pins verified:", json.dumps(manifest["runtime"], sort_keys=True))


if __name__ == "__main__":
    main()
