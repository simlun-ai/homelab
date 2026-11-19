"""Test the OpenTofu state-key lifetime with disposable bytes."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import trust_tofu


class TrustTofuTests(unittest.TestCase):
    def test_key_session_reuses_one_recovery_for_multiple_provider_requests(
        self,
    ) -> None:
        key = bytes(range(32))
        with (
            TemporaryDirectory() as directory,
            patch.object(
                trust_tofu.recovery.secrets,
                "executable",
                return_value="/disposable/homelab-unwrap",
            ),
            patch.object(trust_tofu.tofu_key, "recover", return_value=key) as recover,
        ):
            address = Path(directory) / "key.sock"
            try:
                with trust_tofu.key_session(address):
                    for _ in range(4):
                        self.assertEqual(
                            trust_tofu.tofu_key.read_session_key(address), key
                        )
            except PermissionError:
                if address.exists():
                    raise
                self.skipTest("This environment forbids local Unix sockets")
            recover.assert_called_once_with("/disposable/homelab-unwrap")
            with self.assertRaises(ConnectionRefusedError):
                trust_tofu.tofu_key.read_session_key(address)
