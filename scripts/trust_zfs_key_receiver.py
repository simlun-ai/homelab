"""Receive a Trust ZFS key on the node via kubectl exec stdin."""

import ctypes
import hmac
import os
import resource
import stat
import sys
from pathlib import Path
from uuid import uuid4

MOUNT = Path("/key-directory")
NAME = "data.key"
KEY_BYTES = 32


def check_mount(fd: int) -> None:
    info = os.fstat(fd)
    device = f"{os.major(info.st_dev)}:{os.minor(info.st_dev)}"
    dm_uuid = Path(f"/sys/dev/block/{device}/dm/uuid").read_text().strip()
    if not dm_uuid.startswith("CRYPT-LUKS2-") or not dm_uuid.endswith(
        "-luks2-EPHEMERAL"
    ):
        raise ValueError("Key directory is not on encrypted EPHEMERAL")
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        fields = line.split()
        if fields[2:5] == [device, "/lib/trust-zfs/keys", str(MOUNT)]:
            break
    else:
        raise ValueError("Key directory is not the intended EPHEMERAL mount")
    if (info.st_uid, info.st_gid) != (0, 0) or info.st_mode & 0o022:
        raise ValueError("Unsafe key directory owner or permissions")


def matches(fd: int, key: bytes) -> bool:
    try:
        existing = os.open(NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    except FileNotFoundError:
        return False
    with os.fdopen(existing, "rb") as handle:
        info = os.fstat(handle.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or (info.st_uid, info.st_gid) != (0, 0)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_size != KEY_BYTES
            or not hmac.compare_digest(handle.read(KEY_BYTES + 1), key)
        ):
            raise ValueError("Existing key differs or has unsafe metadata")
    return True


def install(fd: int, key: bytes) -> None:
    if len(key) != KEY_BYTES:
        raise ValueError("Expected exactly 32 key bytes")
    os.fchmod(fd, 0o700)
    if matches(fd, key):
        return
    temporary = ".key-" + uuid4().hex
    handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=fd)
    try:
        with os.fdopen(handle, "wb") as output:
            output.write(key)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(
                temporary, NAME, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False
            )
        except FileExistsError:
            if not matches(fd, key):
                raise
    finally:
        os.unlink(temporary, dir_fd=fd)
    os.fsync(fd)
    if not matches(fd, key):
        raise ValueError("Installed key missing")


def main() -> int:
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        if ctypes.CDLL(None).prctl(4, 0, 0, 0, 0) != 0:
            raise ValueError("Could not disable process dumping")
        if len(Path("/proc/swaps").read_text().splitlines()) != 1:
            raise ValueError("Node swap is enabled")
        fd = os.open(MOUNT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            check_mount(fd)
            if sys.argv[1:] == ["install"]:
                install(fd, sys.stdin.buffer.read(KEY_BYTES + 1))
                print("PASS: root-only ZFS key verified on encrypted EPHEMERAL.")
            elif sys.argv[1:] == ["check"]:
                print("PASS: key destination is on encrypted EPHEMERAL.")
            else:
                raise ValueError("Unexpected action")
        finally:
            os.close(fd)
    except (OSError, ValueError):
        print("ZFS key destination or key verification failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
