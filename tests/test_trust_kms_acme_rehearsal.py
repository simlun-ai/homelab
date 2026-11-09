"""Regression checks for the Trust ACME staging boundary."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import trust_kms_acme_rehearsal as acme


class CertbotRehearsalTests(unittest.TestCase):
    def test_certbot_never_uses_default_paths_or_production(self) -> None:
        workspace = Path("/example/private-ram")
        for renew in (False, True):
            with self.subTest(renew=renew):
                command = acme.certbot_command(
                    workspace, "test@example.org", renew=renew
                )
                self.assertEqual(
                    command[command.index("--server") + 1], acme.STAGING_CA
                )
                self.assertIn("--reuse-key", command)
                for kind in ("config", "work", "logs"):
                    self.assertEqual(
                        command[command.index(f"--{kind}-dir") + 1],
                        str(workspace / kind),
                    )
        self.assertIn(
            "--force-renewal", acme.certbot_command(workspace, "", renew=True)
        )

    def test_mount_check_requires_noswap_on_the_held_tmpfs(self) -> None:
        for entries in (
            "42 1 0:2 / /run rw - tmpfs tmpfs rw",
            "42 1 0:2 / /run rw - ext4 /dev/sda rw,noswap",
            "43 1 0:2 / /run rw - tmpfs tmpfs rw,noswap",
        ):
            with (
                self.subTest(entries=entries),
                patch.object(Path, "read_text", side_effect=["mnt_id:\t42\n", entries]),
                self.assertRaises(acme.RehearsalError),
            ):
                acme.require_noswap_mount(9)
        with patch.object(
            Path,
            "read_text",
            side_effect=["mnt_id:\t42\n", "42 1 0:2 / /run rw - tmpfs tmpfs rw,noswap"],
        ):
            acme.require_noswap_mount(9)

    def test_failed_ram_preflight_never_starts_rehearsal(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(acme, "RAM_ROOT", Path(directory)),
            patch.object(acme, "require_coordinator_hardening"),
            patch.object(
                acme, "require_noswap_mount", side_effect=acme.RehearsalError()
            ),
            patch.object(acme, "rehearse") as rehearse,
            patch.object(acme.resource, "setrlimit"),
            patch.object(acme.os, "umask"),
            patch.object(acme.signal, "signal"),
            patch.object(acme.sys, "argv", ["rehearsal", "test@example.org"]),
            patch("builtins.print"),
        ):
            self.assertEqual(acme.main(), 1)
            rehearse.assert_not_called()
