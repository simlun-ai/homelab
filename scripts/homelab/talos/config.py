"""Assemble, validate and deliver Talos configuration through sealed descriptors."""

import fcntl
import json
import os
import subprocess
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, date, datetime

from . import bootstrap

INSTALL_DISK = "/dev/REHEARSAL-DO-NOT-INSTALL"
# Linux UAPI values; some Python builds omit the symbolic fcntl constants.
F_ADD_SEALS = getattr(fcntl, "F_ADD_SEALS", 1033)
F_GET_SEALS = getattr(fcntl, "F_GET_SEALS", 1034)
SEALS = 0x0001 | 0x0002 | 0x0004 | 0x0008  # SEAL, SHRINK, GROW, WRITE


@contextmanager
def memory_file(content: bytes) -> Generator[int]:
    """Create a private anonymous shmem file, then seal it against modification."""
    fd = os.memfd_create("talos-rehearsal", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        os.fchmod(fd, 0o600)
        remaining = memoryview(content)
        while remaining:
            count = os.write(fd, remaining)
            if count <= 0:
                raise RuntimeError("Cannot fill protected memory descriptor")
            remaining = remaining[count:]
        os.lseek(fd, 0, os.SEEK_SET)
        fcntl.fcntl(fd, F_ADD_SEALS, SEALS)
        if fcntl.fcntl(fd, F_GET_SEALS) & SEALS != SEALS:
            raise RuntimeError("Cannot seal protected memory descriptor")
        yield fd
    finally:
        os.close(fd)


def generate_machine_config(
    talosctl: str,
    bundle: bytes,
    output_type: str,
    *,
    cluster: str,
    endpoint: str,
    talos_version: str,
    kubernetes_version: str,
    public_args: list[str],
) -> bytes:
    with memory_file(bundle) as fd:
        return bootstrap.capture_bundle(
            [
                talosctl,
                "gen",
                "config",
                cluster,
                endpoint,
                "--talos-version",
                talos_version,
                "--kubernetes-version",
                kubernetes_version,
                "--with-secrets",
                f"/proc/self/fd/{fd}",
                *public_args,
                "--install-disk",
                INSTALL_DISK,
                "--with-docs=false",
                "--with-examples=false",
                "--output-types",
                output_type,
                "--output",
                "-",
            ],
            timeout=60,
            pass_fds=(fd,),
        )


def validate_machine(talosctl: str, config: bytes) -> None:
    with memory_file(config) as fd:
        subprocess.run(
            [
                talosctl,
                "validate",
                "--config",
                f"/proc/self/fd/{fd}",
                "--mode",
                "metal",
                "--strict",
            ],
            pass_fds=(fd,),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=60,
        )


def apply_install(talosctl: str, config: bytes, *, node: str) -> None:
    with memory_file(config) as fd:
        subprocess.run(
            [
                talosctl,
                "apply-config",
                "--insecure",
                "--nodes",
                node,
                "--file",
                f"/proc/self/fd/{fd}",
            ],
            pass_fds=(fd,),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=60,
        )


def validate_client(
    talosctl: str, config: bytes, expected_context: str
) -> dict[str, object]:
    with memory_file(config) as fd:
        result = bootstrap.capture_bundle(
            [
                talosctl,
                "config",
                "info",
                "--talosconfig",
                f"/proc/self/fd/{fd}",
                "--output",
                "json",
            ],
            timeout=60,
            pass_fds=(fd,),
        )
    info: dict[str, object] = json.loads(result)
    if info.get("context") != expected_context or info.get("roles") != ["os:admin"]:
        raise ValueError("Unexpected generated client identity or roles")
    expiry = info.get("certNotAfter")
    if not isinstance(expiry, str):
        raise ValueError("Missing client certificate expiry")
    if date.fromisoformat(expiry) <= datetime.now(UTC).date():
        raise ValueError("Generated client certificate is expired")
    return info
