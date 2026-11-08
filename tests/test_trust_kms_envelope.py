"""Codec contract: public fixed vector, rejection paths and independent payloads."""

import base64
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from homelab.trust_kms import envelope as e
from kms_vector import VECTOR as V

KEY = bytes.fromhex(V["key_hex"])
PLAIN = bytes.fromhex(V["plaintext_hex"])
NODE, ID = V["node"], V["key_id"]


class EnvelopeTests(unittest.TestCase):
    def test_independently_computed_public_vector(self) -> None:
        salt, nonce = bytes.fromhex(V["salt_hex"]), bytes.fromhex(V["nonce_hex"])
        self.assertEqual(e.derive(KEY, salt, NODE, ID).hex(), V["derived_key_hex"])
        with patch.object(e.os, "urandom", side_effect=[salt, nonce]):
            encoded = e.seal(KEY, NODE, ID, PLAIN)
        self.assertEqual(encoded.decode(), V["envelope"])
        header = json.loads(encoded)
        del header["ciphertext"]
        self.assertEqual(e.canonical(header).decode(), V["aad"])
        self.assertEqual(e.unseal(KEY, NODE.upper(), ID, encoded), PLAIN)
        self.assertEqual(
            e.unseal(KEY, NODE, ID, json.dumps(json.loads(encoded), indent=2).encode()),
            PLAIN,
        )

    def test_independent_volume_payloads_use_fresh_randomness(self) -> None:
        first, second = e.seal(KEY, NODE, ID, PLAIN), e.seal(KEY, NODE, ID, PLAIN)
        a, b = json.loads(first), json.loads(second)
        for name in ("salt", "nonce", "ciphertext"):
            self.assertNotEqual(a[name], b[name])
        other = e.seal(KEY, NODE, ID, b"x" * 32)
        self.assertEqual(e.unseal(KEY, NODE, ID, first), PLAIN)
        self.assertEqual(e.unseal(KEY, NODE, ID, other), b"x" * 32)

    def test_every_authenticated_field_and_tag_is_bound(self) -> None:
        original = json.loads(V["envelope"])
        changes = {
            "format": "homelab-wrap-v1",
            "encoding": "raw-31",
            "node_uuid": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
            "key_id": ID[:-1] + "2",
        }
        for field in ("salt", "nonce", "ciphertext"):
            value = bytearray(base64.b64decode(original[field]))
            value[-1] ^= 1
            changes[field] = base64.b64encode(value).decode()
        for name, value in changes.items():
            changed = {**original, name: value}
            with (
                self.subTest(field=name),
                self.assertRaisesRegex(e.InvalidArgument, "^INVALID_ARGUMENT$"),
            ):
                e.unseal(KEY, NODE, ID, json.dumps(changed).encode())
        with self.assertRaises(e.InvalidArgument):
            e.unseal(bytes(reversed(KEY)), NODE, ID, V["envelope"].encode())
        # Even when a different context is expected, its edited header must not
        # authenticate with the old ciphertext/AAD/KDF context.
        changed = {**original, "key_id": ID[:-1] + "2"}
        with self.assertRaises(e.InvalidArgument):
            e.unseal(KEY, NODE, changed["key_id"], json.dumps(changed).encode())

    def test_changed_node_cannot_reuse_ciphertext_under_its_own_context(self) -> None:
        changed = json.loads(V["envelope"])
        other = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
        changed["node_uuid"] = other
        with self.assertRaises(e.InvalidArgument):
            e.unseal(KEY, other, ID, json.dumps(changed).encode())

    def test_malformed_and_oversized_envelopes(self) -> None:
        text = V["envelope"]
        original = json.loads(text)
        malformed = [
            b"",
            b"[]",
            b"null",
            b"{",
            b"x" * 4097,
            text.encode() + b"{}",
            ('{"format":"homelab-kms-v1",' + text[1:]).encode(),
            json.dumps({**original, "extra": "x"}).encode(),
            json.dumps({k: v for k, v in original.items() if k != "salt"}).encode(),
            b"[" * 1500 + b"]" * 1500,
        ]
        for name in original:
            for value in (None, list[object](), dict[str, object](), 42, True):
                malformed.append(json.dumps({**original, name: value}).encode())
        for value in (
            "***",
            original["salt"] + "=",
            original["salt"] + "\n",
            "",
            "eA==",
        ):
            malformed.append(json.dumps({**original, "salt": value}).encode())
        for encoded in malformed:
            with (
                self.subTest(size=len(encoded)),
                self.assertRaisesRegex(e.InvalidArgument, "^INVALID_ARGUMENT$"),
            ):
                e.unseal(KEY, NODE, ID, encoded)

    def test_strict_keys_identifiers_and_plaintext_size(self) -> None:
        for node in (
            "0" * 36,
            "00000000-0000-0000-0000-000000000000",
            NODE.replace("-", ""),
            "{" + NODE + "}",
        ):
            with self.assertRaises(e.InvalidArgument):
                e.seal(KEY, node, ID, PLAIN)
        for identifier in (
            "homelab/v1/trust/kms/x/r0",
            "homelab/v1/other/kms/x/r1",
            ID + "\n",
            "x" * 257,
        ):
            with self.assertRaises(e.InvalidArgument):
                e.seal(KEY, NODE, identifier, PLAIN)
        for size in (0, 1, 31, 33, 4096):
            with self.assertRaises(e.InvalidArgument):
                e.seal(KEY, NODE, ID, b"x" * size)
            with self.assertRaises(e.InvalidArgument):
                e.seal(b"x" * size, NODE, ID, PLAIN)

    def test_no_plaintext_or_key_logging(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            e.unseal(KEY, NODE, ID, e.seal(KEY, NODE, ID, PLAIN))
        self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
