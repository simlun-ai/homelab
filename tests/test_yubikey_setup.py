"""Disposable public test material only. No real token or golden key required."""

import io
import unittest
from contextlib import nullcontext, redirect_stderr, redirect_stdout
from unittest.mock import Mock, patch

from yubikit.yubiotp import SLOT

from homelab import yubikey_setup as setup

PUBLIC_TEST_KEY = bytes(range(20))


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
        for answer in (
            "program key0 slot2",
            "replace key0 slot2",
            "replace key1 slot2 and erase existing credential",
        ):
            with (
                self.subTest(answer=answer),
                patch("builtins.input", return_value=answer),
                patch.object(setup, "verify_token") as verify,
                redirect_stdout(self.output),
            ):
                with self.assertRaises(RuntimeError):
                    setup.program(self.session, "key0", PUBLIC_TEST_KEY, replace=True)
                self.session.put_configuration.assert_not_called()
                verify.assert_not_called()

    def test_replacement_writes_only_slot_two_then_verifies(self):
        self.session.get_config_state.return_value.is_configured.return_value = True
        operations = []
        self.session.put_configuration.side_effect = lambda *args: operations.append(
            "write"
        )
        with (
            patch(
                "builtins.input",
                return_value="replace key0 slot2 and erase existing credential",
            ) as prompt,
            patch.object(
                setup,
                "verify_token",
                side_effect=lambda *args: operations.append("verify"),
            ) as verify,
            redirect_stdout(self.output),
        ):
            setup.program(self.session, "key0", PUBLIC_TEST_KEY, replace=True)
        self.assertIn(
            "replace key0 slot2 and erase existing credential", prompt.call_args.args[0]
        )
        self.session.put_configuration.assert_called_once()
        self.assertEqual(self.session.put_configuration.call_args.args[0], SLOT.TWO)
        self.assertEqual(operations, ["write", "verify"])
        verify.assert_called_once_with(self.session, PUBLIC_TEST_KEY)
        self.assertIn(
            "overwrites the existing slot 2 credential", self.output.getvalue()
        )
        self.assertNotIn(PUBLIC_TEST_KEY.hex(), self.output.getvalue())

    def test_cli_passes_explicit_replacement_to_program(self):
        self.session.get_config_state.return_value.is_configured.return_value = True
        with (
            patch.object(
                setup.sys,
                "argv",
                ["yubikey_cli", "program", "--label", "key0", "--replace"],
            ),
            patch.object(setup, "harden"),
            patch.object(setup, "describe"),
            patch.object(setup, "token", return_value=nullcontext(self.session)),
            patch.object(setup, "read_golden_key", return_value=PUBLIC_TEST_KEY),
            patch.object(setup, "program") as program,
        ):
            setup.main()
        program.assert_called_once_with(
            self.session, "key0", PUBLIC_TEST_KEY, replace=True
        )

    def test_cli_replacement_flag_rejected_before_hardware_for_other_commands(self):
        for command in ("inspect", "verify", "verify-set"):
            with (
                self.subTest(command=command),
                patch.object(
                    setup.sys,
                    "argv",
                    ["yubikey_cli", command, "--label", "key0", "--replace"],
                ),
                patch.object(setup, "harden") as harden,
                patch.object(setup, "token") as token,
                redirect_stderr(self.output),
            ):
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

    def test_program_targets_slot_two_with_fixed_input_and_touch(self):
        for occupied in (False, True):
            with self.subTest(occupied=occupied):
                self.session.reset_mock()
                self.session.get_config_state.return_value.is_configured.return_value = occupied
                with (
                    patch.object(setup, "confirm"),
                    patch.object(setup, "verify_token") as verify,
                    redirect_stdout(self.output),
                ):
                    setup.program(
                        self.session, "key0", PUBLIC_TEST_KEY, replace=occupied
                    )
                args = self.session.put_configuration.call_args.args
                self.assertEqual(args[0], SLOT.TWO)
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

    def test_hidden_input_preserves_leading_zeros_and_checks_confirmation(self):
        value = "00" * 2 + "a1" * 18
        with patch.object(setup.getpass, "getpass", side_effect=[value, value.upper()]):
            self.assertEqual(setup.read_golden_key(), bytes.fromhex(value))
        with (
            patch.object(setup.getpass, "getpass", side_effect=[value, "11" * 20]),
            self.assertRaises(ValueError),
        ):
            setup.read_golden_key()

    def test_occupied_slot_one_does_not_block_programming_slot_two(self):
        self.session.get_config_state.return_value.is_configured.side_effect = (
            lambda slot: slot == SLOT.ONE
        )
        with (
            patch.object(setup, "confirm"),
            patch.object(setup, "verify_token"),
            redirect_stdout(self.output),
        ):
            setup.program(self.session, "key0", PUBLIC_TEST_KEY)
        self.assertEqual(self.session.put_configuration.call_args.args[0], SLOT.TWO)

    def test_old_slot_one_confirmation_is_rejected(self):
        with (
            patch("builtins.input", return_value="program key0 slot1"),
            self.assertRaises(RuntimeError),
        ):
            setup.confirm("key0", "program")

    def test_verify_rejects_wrong_golden_key(self):
        self.session.get_config_state.return_value.is_configured.return_value = True
        with (
            patch.object(setup, "require_no_response_without_touch"),
            patch.object(setup, "respond", return_value=b"x" * 20),
            self.assertRaises(RuntimeError),
        ):
            setup.verify_token(self.session, PUBLIC_TEST_KEY)


if __name__ == "__main__":
    unittest.main()
