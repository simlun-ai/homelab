"""Disposable secrets only; no physical token or SSH connection."""

import hmac
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from homelab import coordinator_password as passwords
from submodule_fixture import prepare_store


def respond(challenge: bytes) -> bytes:
    return hmac.digest(bytes(range(20)), challenge, "sha1")


class PasswordTests(unittest.TestCase):
    def test_create_recover_distinct_and_no_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            prepare_store(repo)
            values: list[bytes] = []
            for host in passwords.HOSTS:
                passwords.create(host, respond, repo)
                value = passwords.recover(host, respond, repo)
                values.append(value)
                record = passwords.record_path(host, repo).read_bytes()
                self.assertNotIn(value, record)
                with self.assertRaises(FileExistsError):
                    passwords.create(host, respond, repo)
                self.assertEqual(record, passwords.record_path(host, repo).read_bytes())
            self.assertEqual(len(set(values)), 3)

    def test_wrong_host_rejected_before_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            prepare_store(repo)
            passwords.create("ups-aux", respond, repo)
            passwords.record_path("ups-pi", repo).write_bytes(
                passwords.record_path("ups-aux", repo).read_bytes()
            )
            token = Mock(side_effect=AssertionError("Must not query token"))
            with self.assertRaises(ValueError):
                passwords.recover("ups-pi", token, repo)
            token.assert_not_called()

    def test_failed_verification_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            prepare_store(repo)
            with patch.object(passwords.wrapping, "unwrap", return_value=b"wrong"):
                with self.assertRaises(ValueError):
                    passwords.create("ups-aux", respond, repo)
            self.assertFalse(passwords.record_path("ups-aux", repo).exists())

    def test_delivery_only_in_stdin(self) -> None:
        dummy = b"A" * 43
        with (
            patch.object(passwords.coordinator_ssh, "check"),
            patch.object(passwords.subprocess, "run") as run,
        ):
            passwords.apply("ups-pi", dummy)
            args, kwargs = run.call_args
            self.assertNotIn(dummy.decode(), " ".join(args[0]))
            self.assertEqual(kwargs["input"], b"administrator:" + dummy + b"\n")
            self.assertIn("StrictHostKeyChecking=yes", args[0])
            self.assertIn("-T", args[0])
            with self.assertRaises(ValueError):
                passwords.apply("ups-pi", b"bad\nroot:injection")
            self.assertEqual(run.call_count, 1)

    def test_manifest_agrees_with_fixed_contexts(self) -> None:
        manifest = json.loads((passwords.REPO / "secrets/manifest.json").read_text())
        self.assertEqual(
            [
                record
                for record in manifest["records"]
                if "/local-password/" in record["key_id"]
            ],
            [
                dict(
                    key_id=passwords.context(host),
                    root_key=passwords.ROOT_KEY,
                    file="wrapped/" + passwords.record_path(host).name,
                )
                for host in passwords.HOSTS
            ],
        )
