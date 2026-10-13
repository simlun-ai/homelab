"""Require the private submodule before touching wrapped credential records."""
from pathlib import Path
import subprocess


class StoreUnavailable(RuntimeError):
    pass


def require_store(repo):
    repo = Path(repo).resolve()
    store = repo / 'secrets/wrapped'
    message = ('Private secrets submodule unavailable. From the repository root run: '
               'git submodule update --init --recursive -- secrets/wrapped')
    try:
        if store.is_symlink() or not (store / '.git').exists():
            raise StoreUnavailable(message)
        def git(directory, *args):
            return subprocess.check_output(
                ['git', '-C', str(directory), *args], stderr=subprocess.DEVNULL,
                text=True, timeout=10).strip()
        entry = git(repo, 'ls-files', '--stage', '--', 'secrets/wrapped')
        if not entry.startswith('160000 ') or not entry.endswith('\tsecrets/wrapped'):
            raise StoreUnavailable(message)
        if Path(git(store, 'rev-parse', '--show-toplevel')).resolve() != store:
            raise StoreUnavailable(message)
        git(store, 'rev-parse', '--verify', 'HEAD')
    except (OSError, subprocess.SubprocessError) as exc:
        raise StoreUnavailable(message) from exc
    return store
