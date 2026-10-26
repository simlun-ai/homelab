"""Parent/library contract using only the component's public disposable fake key."""

import base64
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import ExitStack, redirect_stderr
from pathlib import Path

from cryptography.exceptions import InvalidTag
from homelab_secrets import wrapping
from homelab_secrets.cli import FAKE_ROOT, fake_responder

from homelab import coordinator_password as passwords, coordinator_ssh as ssh
from submodule_fixture import prepare_store


class WrappedSecretsIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.contexts = ExitStack()
        self.addCleanup(self.contexts.close)
        self.contexts.enter_context(redirect_stderr(io.StringIO()))
        self.respond = self.contexts.enter_context(fake_responder())
        self.manifest = json.loads(
            (passwords.REPO / 'secrets/manifest.json').read_text())['records']

    def test_manifest_identifiers_and_complete_record_round_trip(self):
        for entry in self.manifest:
            key_id = entry['key_id']
            self.assertEqual(wrapping.challenge(key_id),
                             hashlib.sha256(key_id.encode('ascii')).hexdigest().encode('ascii'))
            for plaintext in (b'', b'public dummy password', bytes(range(256)) + b'\n'):
                with self.subTest(key_id=key_id, size=len(plaintext)):
                    encoded = wrapping.wrap(plaintext, key_id, FAKE_ROOT, 1, self.respond)
                    self.assertIsInstance(encoded, bytes)
                    record = json.loads(encoded)
                    self.assertEqual(set(record), {
                        'format', 'key_id', 'root_key', 'revision', 'salt', 'nonce', 'ciphertext'})
                    self.assertEqual(record['format'], 'homelab-wrap-v1')
                    self.assertEqual(record['key_id'], key_id)
                    self.assertEqual(record['root_key'], 'golden-fake-1')
                    self.assertEqual(record['revision'], 1)
                    self.assertEqual(len(base64.b64decode(record['salt'], validate=True)), 32)
                    self.assertEqual(len(base64.b64decode(record['nonce'], validate=True)), 12)
                    self.assertEqual(len(base64.b64decode(record['ciphertext'], validate=True)),
                                     len(plaintext) + 16)
                    # Consumers read JSON files with a trailing newline.
                    self.assertEqual(wrapping.unwrap(encoded + b'\n', key_id, FAKE_ROOT,
                                                     self.respond), plaintext)

    def test_wrong_context_and_malformed_record_fail_before_response(self):
        key_id = self.manifest[0]['key_id']
        encoded = wrapping.wrap(b'public dummy', key_id, FAKE_ROOT, 1, self.respond)

        def forbidden_response(challenge):
            self.fail('Invalid record queried the responder')

        for record, expected_id, expected_root in (
            (encoded, self.manifest[1]['key_id'], FAKE_ROOT),
            (encoded, key_id, 'golden-1'),
            (b'{}', key_id, FAKE_ROOT),
            (b'{', key_id, FAKE_ROOT),
        ):
            with self.subTest(key_id=expected_id, root=expected_root), self.assertRaises(ValueError):
                wrapping.unwrap(record, expected_id, expected_root, forbidden_response)

    def test_tampered_ciphertext_is_rejected(self):
        key_id = self.manifest[0]['key_id']
        record = json.loads(wrapping.wrap(b'public dummy', key_id, FAKE_ROOT, 1, self.respond))
        ciphertext = bytearray(base64.b64decode(record['ciphertext']))
        ciphertext[0] ^= 1
        record['ciphertext'] = base64.b64encode(ciphertext).decode('ascii')
        with self.assertRaises(InvalidTag):
            wrapping.unwrap(json.dumps(record).encode(), key_id, FAKE_ROOT, self.respond)

    def test_password_consumers_use_real_wrapping_with_injected_fake_response(self):
        # The callback is test-only; production context/root identifiers stay intact.
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            prepare_store(repo)
            for host in passwords.HOSTS:
                with self.subTest(host=host):
                    passwords.create(host, self.respond, repo)
                    encoded = passwords.record_path(host, repo).read_bytes()
                    record = json.loads(encoded)
                    self.assertEqual(record['root_key'], 'golden-1')
                    self.assertEqual(record['key_id'], passwords.context(host))
                    recovered = passwords.recover(host, self.respond, repo)
                    self.assertRegex(recovered, rb'^[A-Za-z0-9_-]{43}$')
                    self.assertEqual(wrapping.unwrap(encoded, passwords.context(host),
                                                     'golden-1', self.respond), recovered)

    def test_ssh_consumer_uses_real_wrapping_with_injected_fake_response(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            prepare_store(repo)
            ssh.create(self.respond, repo)
            encoded = (repo / ssh.RECORD).read_bytes()
            record = json.loads(encoded)
            self.assertEqual(record['root_key'], 'golden-1')
            self.assertEqual(record['key_id'], ssh.KEY_ID)
            private, public = ssh.recover(self.respond, repo)
            self.assertEqual(public, ssh.read_public(repo))
            self.assertEqual(wrapping.unwrap(encoded, ssh.KEY_ID, 'golden-1', self.respond),
                             private)
