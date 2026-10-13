from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import Mock
from homelab.record_store import require_store, StoreUnavailable
from homelab import coordinator_password, coordinator_ssh
from submodule_fixture import prepare_store


class RecordStoreTests(unittest.TestCase):
    def test_missing_store_fails_before_generation_or_token(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            token = Mock()
            for operation in (lambda: coordinator_password.create('ups-aux', token, repo),
                              lambda: coordinator_ssh.create(token, repo),
                              lambda: coordinator_password.recover('ups-aux', token, repo),
                              lambda: coordinator_ssh.recover(token, repo)):
                with self.assertRaisesRegex(StoreUnavailable, 'git submodule update'):
                    operation()
            token.assert_not_called()
            self.assertEqual(list(repo.iterdir()), [])

    def test_plain_directory_is_not_submodule(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / 'secrets/wrapped').mkdir(parents=True)
            with self.assertRaises(StoreUnavailable):
                require_store(repo)

    def test_initialized_gitlink_works(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            prepare_store(repo)
            self.assertEqual(require_store(repo), repo / 'secrets/wrapped')

    def test_absorbed_submodule_gitfile_works(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            store = prepare_store(repo)
            def git(*args):
                subprocess.run(['git', '-C', str(repo), *args], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            git('config', '-f', '.gitmodules', 'submodule.secrets/wrapped.path', 'secrets/wrapped')
            git('config', '-f', '.gitmodules', 'submodule.secrets/wrapped.url', 'unused-test-url')
            git('submodule', 'absorbgitdirs', 'secrets/wrapped')
            self.assertTrue((store / '.git').is_file())
            self.assertEqual(require_store(repo), store)

