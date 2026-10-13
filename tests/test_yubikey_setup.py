"""Disposable public test material only. No real token or golden key required."""

import base64
from contextlib import nullcontext, redirect_stderr, redirect_stdout
import hashlib
import hmac
import io
import json
import unittest
from unittest.mock import Mock, patch

from cryptography.exceptions import InvalidTag
from yubikit.core.otp import STATUS_UPNEEDED
from yubikit.yubiotp import SLOT

from homelab import wrapping
from homelab import yubikey_setup as setup

PUBLIC_TEST_KEY = bytes(range(20))
ID = "homelab/v1/test/wrapping/fixture/r1"
ROOT = "test-only"


def software(challenge):
    return hmac.digest(PUBLIC_TEST_KEY, challenge, "sha1")


class WrappingTests(unittest.TestCase):
    def setUp(self):
        self.record = wrapping.wrap(b"disposable dummy", ID, ROOT, 1, software)

    def rewrite(self, **changes):
        data = json.loads(self.record)
        data.update(changes)
        return json.dumps(data).encode()

    def test_hmac_rfc2202_vector_and_challenge(self):
        self.assertEqual(hmac.digest(b"\x0b" * 20, b"Hi There", "sha1").hex(),
                         "b617318655057264e28bc0b6fb378c8ef146be00")
        self.assertEqual(wrapping.challenge(ID), hashlib.sha256(ID.encode()).hexdigest().encode())
        self.assertEqual(len(wrapping.challenge(ID)), 64)

    def test_known_hkdf_info_and_header_encoding(self):
        header = {"format": "homelab-wrap-v1", "key_id": ID, "root_key": ROOT,
                  "revision": 9007199254740991, "salt": "ab/+==", "nonce": "cd/+=="}
        expected = ('{"format":"homelab-wrap-v1","key_id":"' + ID +
                    '","nonce":"cd/+==","revision":9007199254740991,"root_key":"test-only","salt":"ab/+=="}').encode()
        self.assertEqual(wrapping.canonical_header(header), expected)
        # Independent RFC 5869 extract/expand for the format's actual context.
        salt = bytes(range(32))
        prk = hmac.digest(salt, b"r" * 20, "sha256")
        expected_key = hmac.digest(prk, b"homelab-wrap-v1\0test-only\0" + ID.encode() + b"\x01", "sha256")
        self.assertEqual(wrapping.derive(b"r" * 20, salt, ROOT, ID), expected_key)

    def test_roundtrip_uses_fresh_salt_and_nonce(self):
        other = json.loads(wrapping.wrap(b"disposable dummy", ID, ROOT, 1, software))
        first = json.loads(self.record)
        self.assertNotEqual(other["salt"], first["salt"])
        self.assertNotEqual(other["nonce"], first["nonce"])
        self.assertEqual(wrapping.unwrap(self.record, ID, ROOT, software), b"disposable dummy")

    def test_validation_precedes_token_access(self):
        missing = json.loads(self.record)
        del missing["salt"]
        invalid = [b"[]", b"{", b"{" + self.record[1:-1] + b',"revision":2}',
                   json.dumps(missing).encode(), self.rewrite(extra="field"),
                   self.rewrite(revision=True), self.rewrite(revision=0),
                   self.rewrite(revision=9007199254740992), self.rewrite(revision=1.0),
                   self.rewrite(format="unknown"), self.rewrite(key_id=ID + "/wrong"),
                   self.rewrite(root_key="wrong"), self.rewrite(salt="abc"),
                   self.rewrite(nonce=base64.b64encode(b"n" * 11).decode()),
                   self.rewrite(ciphertext=base64.b64encode(b"x" * 15).decode()),
                   self.rewrite(salt=json.loads(self.record)["salt"] + "\n"),
                   b" " * (wrapping.MAX_RECORD + 1)]
        for encoded in invalid:
            with self.subTest(length=len(encoded)):
                responder = Mock(side_effect=AssertionError("Token must not be queried"))
                with self.assertRaises(ValueError):
                    wrapping.unwrap(encoded, ID, ROOT, responder)
                responder.assert_not_called()

    def test_authenticated_fields_and_ciphertext_tampering(self):
        data = json.loads(self.record)
        for field in ("salt", "nonce", "ciphertext"):
            raw = bytearray(base64.b64decode(data[field]))
            raw[0] ^= 1
            with self.subTest(field=field), self.assertRaises(InvalidTag):
                wrapping.unwrap(self.rewrite(**{field: base64.b64encode(raw).decode()}), ID, ROOT, software)
        with self.assertRaises(InvalidTag):
            wrapping.unwrap(self.rewrite(revision=2), ID, ROOT, software)
        with self.assertRaises(InvalidTag):
            wrapping.unwrap(self.record, ID, ROOT, lambda _: b"x" * 20)

    def test_context_and_input_limits(self):
        for bad in (ID.upper(), ID + "\n", ID.replace("fixture", ""), ID.replace("/r1", "/r0")):
            with self.subTest(identifier=bad), self.assertRaises(ValueError):
                wrapping.challenge(bad)
        with self.assertRaises(ValueError):
            wrapping.wrap(b"x" * (wrapping.MAX_PLAINTEXT + 1), ID, ROOT, 1, software)
        with self.assertRaises(ValueError):
            wrapping.wrap(b"test", ID, ROOT, 1, lambda _: b"short")


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock()
        self.session.get_config_state.return_value.is_configured.return_value = False
        self.output = io.StringIO()

    def test_program_refuses_occupied_slot_before_confirmation(self):
        self.session.get_config_state.return_value.is_configured.return_value = True
        with patch.object(setup, "confirm") as confirm, self.assertRaises(RuntimeError):
            setup.program(self.session, "key0", PUBLIC_TEST_KEY)
        confirm.assert_not_called()
        self.session.put_configuration.assert_not_called()

    def test_replacement_requires_full_erase_confirmation(self):
        self.session.get_config_state.return_value.is_configured.return_value = True
        for answer in ("program key0 slot1", "replace key0 slot1",
                       "replace key1 slot1 and erase existing credential"):
            with self.subTest(answer=answer), patch("builtins.input", return_value=answer), \
                    patch.object(setup, "verify_token") as verify, redirect_stdout(self.output):
                with self.assertRaises(RuntimeError):
                    setup.program(self.session, "key0", PUBLIC_TEST_KEY, replace=True)
                self.session.put_configuration.assert_not_called()
                verify.assert_not_called()

    def test_replacement_writes_only_slot_one_then_verifies(self):
        self.session.get_config_state.return_value.is_configured.return_value = True
        operations = []
        self.session.put_configuration.side_effect = lambda *args: operations.append("write")
        with patch("builtins.input", return_value="replace key0 slot1 and erase existing credential") as prompt, \
                patch.object(setup, "verify_token", side_effect=lambda *args: operations.append("verify")) as verify, \
                redirect_stdout(self.output):
            setup.program(self.session, "key0", PUBLIC_TEST_KEY, replace=True)
        self.assertIn("replace key0 slot1 and erase existing credential", prompt.call_args.args[0])
        self.session.put_configuration.assert_called_once()
        self.assertEqual(self.session.put_configuration.call_args.args[0], SLOT.ONE)
        self.assertEqual(operations, ["write", "verify"])
        verify.assert_called_once_with(self.session, PUBLIC_TEST_KEY)
        self.assertIn("overwrites the existing slot 1 credential", self.output.getvalue())
        self.assertNotIn(PUBLIC_TEST_KEY.hex(), self.output.getvalue())

    def test_cli_passes_explicit_replacement_to_program(self):
        self.session.get_config_state.return_value.is_configured.return_value = True
        with patch.object(setup.sys, "argv", ["yubikey_cli", "program", "--label", "key0", "--replace"]), \
                patch.object(setup, "harden"), patch.object(setup, "describe"), \
                patch.object(setup, "token", return_value=nullcontext(self.session)), \
                patch.object(setup, "read_golden_key", return_value=PUBLIC_TEST_KEY), \
                patch.object(setup, "program") as program:
            setup.main()
        program.assert_called_once_with(self.session, "key0", PUBLIC_TEST_KEY, replace=True)

    def test_cli_replacement_flag_rejected_before_hardware_for_other_commands(self):
        for command in ("inspect", "verify", "verify-set"):
            with self.subTest(command=command), \
                    patch.object(setup.sys, "argv", ["yubikey_cli", command, "--label", "key0", "--replace"]), \
                    patch.object(setup, "harden") as harden, patch.object(setup, "token") as token, \
                    redirect_stderr(self.output):
                with self.assertRaises(SystemExit) as error:
                    setup.main()
                self.assertEqual(error.exception.code, 2)
                harden.assert_not_called()
                token.assert_not_called()

    def test_program_rejects_wrong_key_length_without_writing(self):
        for golden in (b"short", b"x" * 21):
            with self.assertRaises(ValueError):
                setup.program(self.session, "key0", golden)
        self.session.put_configuration.assert_not_called()

    def test_program_targets_slot_one_with_fixed_input_and_touch(self):
        for occupied in (False, True):
            with self.subTest(occupied=occupied):
                self.session.reset_mock()
                self.session.get_config_state.return_value.is_configured.return_value = occupied
                with patch.object(setup, "confirm"), patch.object(setup, "verify_token") as verify, redirect_stdout(self.output):
                    setup.program(self.session, "key0", PUBLIC_TEST_KEY, replace=occupied)
                args = self.session.put_configuration.call_args.args
                self.assertEqual(args[0], SLOT.ONE)
                encoded = args[1].get_config()
                # OTP config: fixed-size[44], extended[45], ticket[46], config[47].
                self.assertTrue(encoded[46] & 0x40)  # CHAL_RESP
                self.assertTrue(encoded[47] & 0x02)  # HMAC mode (0x22)
                self.assertTrue(encoded[47] & 0x08)  # CHAL_BTN_TRIG
                self.assertFalse(encoded[47] & 0x04)  # HMAC_LT64 must be clear
                self.assertFalse(encoded[45] & 0x20)  # ALLOW_UPDATE disabled
                self.session.put_configuration.assert_called_once()
                verify.assert_called_once_with(self.session, PUBLIC_TEST_KEY)
                self.assertNotIn(PUBLIC_TEST_KEY.hex(), self.output.getvalue())

    def test_no_touch_probe_rejects_immediate_response(self):
        self.session.calculate_hmac_sha1.return_value = b"r" * 20
        with redirect_stdout(self.output), self.assertRaises(RuntimeError):
            setup.require_no_response_without_touch(self.session)

    def test_no_touch_probe_requires_actual_touch_request(self):
        self.session.calculate_hmac_sha1.side_effect = setup.TokenTimeout("private failure detail")
        with redirect_stdout(self.output), self.assertRaises(RuntimeError):
            setup.require_no_response_without_touch(self.session)

    def test_no_touch_probe_cancels_confirmed_touch_request(self):
        def pending(slot, challenge, event, keepalive):
            keepalive(STATUS_UPNEEDED)
            self.assertTrue(event.is_set())
            raise setup.TokenTimeout("private failure detail")
        self.session.calculate_hmac_sha1.side_effect = pending
        with redirect_stdout(self.output):
            setup.require_no_response_without_touch(self.session)
        self.assertNotIn("private failure detail", self.output.getvalue())

    def test_hidden_input_preserves_leading_zeros_and_checks_confirmation(self):
        value = "00" * 2 + "a1" * 18
        with patch.object(setup.getpass, "getpass", side_effect=[value, value.upper()]):
            self.assertEqual(setup.read_golden_key(), bytes.fromhex(value))
        with patch.object(setup.getpass, "getpass", side_effect=[value, "11" * 20]), self.assertRaises(ValueError):
            setup.read_golden_key()

    def test_verify_rejects_wrong_golden_key(self):
        self.session.get_config_state.return_value.is_configured.return_value = True
        with patch.object(setup, "require_no_response_without_touch"), patch.object(setup, "respond", return_value=b"x" * 20), self.assertRaises(RuntimeError):
            setup.verify_token(self.session, PUBLIC_TEST_KEY)


if __name__ == "__main__":
    unittest.main()
