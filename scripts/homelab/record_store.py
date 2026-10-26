"""Require the private submodule before touching wrapped credential records."""

import subprocess
from pathlib import Path


class StoreUnavailable(RuntimeError):
    pass


def require_store(repo: Path) -> Path:
    repo = Path(repo).resolve()
    store = repo / "secrets/wrapped"
    message = (
        "Private records submodule unavailable or missing its pinned history. From the repository root run: "
        "git submodule update --init --recursive -- secrets/wrapped"
    )
    try:
        if store.is_symlink() or not (store / ".git").exists():
            raise StoreUnavailable(message)

        def git(directory: Path, *args: str) -> str:
            return subprocess.check_output(
                ["git", "-C", str(directory), *args],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=10,
            ).strip()

        entry = git(repo, "ls-files", "--stage", "--", "secrets/wrapped")
        if not entry.startswith("160000 ") or not entry.endswith("\tsecrets/wrapped"):
            raise StoreUnavailable(message)
        if Path(git(store, "rev-parse", "--show-toplevel")).resolve() != store:
            raise StoreUnavailable(message)
        # Reject a stale code checkout left at this path after the repository split.
        # New credential commits may advance beyond the parent pin.
        git(store, "merge-base", "--is-ancestor", entry.split()[1], "HEAD")
    except (OSError, subprocess.SubprocessError) as exc:
        raise StoreUnavailable(message) from exc
    return store
