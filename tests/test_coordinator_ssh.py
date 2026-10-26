"""Public disposable HMAC root; generated test private keys stay in memory."""

import hmac
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import load_ssh_private_key
from homelab_secrets import wrapping

from homelab import coordinator_ssh as ssh
from submodule_fixture import prepare_store


def respond(challenge):
    return hmac.digest(bytes(range(20)), challenge, "sha1")


class CoordinatorSSHTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        prepare_store(self.repo)

    def test_create_wraps_unencrypted_ed25519_and_refuses_overwrite(self):
        ssh.create(respond, self.repo)
        private, public = ssh.recover(respond, self.repo)
        self.assertIsInstance(load_ssh_private_key(private, None), Ed25519PrivateKey)
        self.assertEqual(public, ssh.read_public(self.repo))
        self.assertNotIn(private, (self.repo / ssh.RECORD).read_bytes())
        self.assertEqual(
            set(
                p.relative_to(self.repo)
                for p in self.repo.rglob("*")
                if p.is_file() and ".git" not in p.parts
            ),
            {ssh.RECORD, ssh.PUBLIC},
        )
        original = (self.repo / ssh.RECORD).read_bytes()
        with self.assertRaises(FileExistsError):
            ssh.create(respond, self.repo)
        self.assertEqual(original, (self.repo / ssh.RECORD).read_bytes())

    def test_no_files_if_wrap_verification_fails(self):
        with patch.object(wrapping, "unwrap", return_value=b"wrong"):
            with self.assertRaises(ValueError):
                ssh.create(respond, self.repo)
        self.assertFalse((self.repo / ssh.RECORD).exists())
        self.assertFalse((self.repo / ssh.PUBLIC).exists())

    def test_restore_missing_public_without_changing_identity(self):
        ssh.create(respond, self.repo)
        public = (self.repo / ssh.PUBLIC).read_bytes()
        (self.repo / ssh.PUBLIC).unlink()
        ssh.restore_public(respond, self.repo)
        self.assertEqual(public, (self.repo / ssh.PUBLIC).read_bytes())

    def test_load_streams_private_and_checks_agent(self):
        ssh.create(respond, self.repo)
        with patch.object(ssh, "agent") as agent:
            ssh.load(respond, self.repo)
        args, kwargs = agent.call_args_list[0]
        self.assertEqual(args, ("-t", "1h", "-"))
        self.assertIsInstance(
            load_ssh_private_key(kwargs["input"], None), Ed25519PrivateKey
        )
        self.assertEqual(
            agent.call_args_list[1].args, ("-T", str(self.repo / ssh.PUBLIC))
        )

    def test_mismatch_never_reaches_agent(self):
        ssh.create(respond, self.repo)
        replacement = Ed25519PrivateKey.generate().public_key()
        (self.repo / ssh.PUBLIC).write_bytes(ssh.public_bytes(replacement) + b"\n")
        with patch.object(ssh, "agent") as agent:
            with self.assertRaises(ValueError):
                ssh.load(respond, self.repo)
        agent.assert_not_called()

    def test_context_substitution_rejected_before_token(self):
        ssh.create(respond, self.repo)
        record = json.loads((self.repo / ssh.RECORD).read_bytes())
        record["key_id"] = "homelab/v1/ups-pi/local-password/administrator/r1"
        (self.repo / ssh.RECORD).write_text(json.dumps(record))
        token = Mock()
        with self.assertRaises(ValueError):
            ssh.recover(token, self.repo)
        token.assert_not_called()

    def test_ciphertext_tamper_never_reaches_agent(self):
        ssh.create(respond, self.repo)
        record = json.loads((self.repo / ssh.RECORD).read_bytes())
        text = record["ciphertext"]
        record["ciphertext"] = ("A" if text[0] != "A" else "B") + text[1:]
        (self.repo / ssh.RECORD).write_text(json.dumps(record))
        with patch.object(ssh, "agent") as agent:
            with self.assertRaises(InvalidTag):
                ssh.load(respond, self.repo)
        agent.assert_not_called()

    def test_agent_requires_socket_and_suppresses_output(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(ssh.subprocess, "run") as run,
        ):
            with self.assertRaises(RuntimeError):
                ssh.agent("-T", "public")
            run.assert_not_called()
        with (
            patch.dict(os.environ, {"SSH_AUTH_SOCK": "/test/socket"}),
            patch.object(ssh.subprocess, "run") as run,
        ):
            ssh.agent("-t", "1h", "-", input=b"disposable")
            args, kwargs = run.call_args
            self.assertEqual(args[0], ["ssh-add", "-t", "1h", "-"])
            self.assertEqual(kwargs["input"], b"disposable")
            self.assertEqual(kwargs["stderr"], ssh.subprocess.DEVNULL)

    def test_manifest_context(self):
        manifest = json.loads((ssh.REPO / "secrets/manifest.json").read_text())
        self.assertIn(
            dict(
                key_id=ssh.KEY_ID,
                root_key=ssh.ROOT_KEY,
                file="wrapped/" + ssh.RECORD.name,
            ),
            manifest["records"],
        )
