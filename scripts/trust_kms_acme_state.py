"""Bounded Certbot state snapshots; plaintext is used only in protected RAM."""

import base64
import json
import os
from pathlib import Path, PurePosixPath
from typing import cast

from trust_kms_acme_profile import profile

LIMIT = 1024 * 1024
WORKSPACE = Path("/run/trust-kms-acme/session")


def snapshot(workspace: Path, *, environment: str = "staging") -> bytes:
    entries: dict[str, dict[str, str]] = {}
    root = workspace / "config"
    for path in sorted(root.rglob("*")):
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            if not path.resolve(strict=True).is_relative_to(root):
                raise ValueError("Escaping state link")
            entries[name] = {"link": os.readlink(path)}
        elif path.is_file():
            entries[name] = {
                "data": base64.b64encode(path.read_bytes()).decode("ascii")
            }
        elif not path.is_dir():
            raise ValueError("Unexpected state entry")
    data = json.dumps(
        {"format": profile(environment).format, "entries": entries}
    ).encode()
    if len(data) > LIMIT or not entries:
        raise ValueError("Invalid state size")
    return data


def restore(workspace: Path, data: bytes, *, environment: str = "staging") -> None:
    if len(data) > LIMIT:
        raise ValueError("State too large")
    value = json.loads(data)
    if value["format"] != profile(environment).format:
        raise ValueError("Unexpected state format")
    entries = cast(dict[str, dict[str, str]], value["entries"])
    if type(entries) is not dict or not entries or len(entries) > 512:
        raise ValueError("Invalid state entries")
    root = workspace / "config"
    root.mkdir(mode=0o700)
    # Create all regular files before links, and never traverse a restored link.
    links: list[tuple[Path, str]] = []
    for name, entry in entries.items():
        if type(name) is not str or type(entry) is not dict:
            raise ValueError("Invalid entry")
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or str(relative) != name:
            raise ValueError("Invalid state path")
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if set(entry) == {"data"}:
            content = base64.b64decode(entry["data"], validate=True)
            with path.open("xb") as stream:
                stream.write(content)
        elif set(entry) == {"link"} and type(entry["link"]) is str:
            links.append((path, entry["link"]))
        else:
            raise ValueError("Invalid state entry")
    for path, target in links:
        if Path(target).is_absolute() or not (
            path.parent / target
        ).resolve().is_relative_to(root):
            raise ValueError("Escaping state link")
        path.symlink_to(target)
    # Resolving every link also rejects broken links and link chains escaping root.
    for path, _ in links:
        if not path.resolve(strict=True).is_relative_to(root):
            raise ValueError("Escaping state link")
