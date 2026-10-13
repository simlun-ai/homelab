"""Local-only Git fixture; never fetches a repository or uses real secrets."""
import subprocess


def prepare_store(repo):
    def git(path, *args):
        return subprocess.check_output(['git', '-C', str(path), *args],
                                       stderr=subprocess.DEVNULL, text=True).strip()
    git(repo, 'init', '-q')
    store = repo / 'secrets/wrapped'
    store.mkdir(parents=True)
    git(store, 'init', '-q')
    git(store, '-c', 'user.name=Test', '-c', 'user.email=test@localhost',
        '-c', 'commit.gpgsign=false', 'commit', '--allow-empty', '-qm', 'Fixture')
    sha = git(store, 'rev-parse', 'HEAD')
    git(repo, 'update-index', '--add', '--cacheinfo', f'160000,{sha},secrets/wrapped')
    return store
