"""Check that maintenance discovery protects Backup's install targets."""

import unittest
from unittest.mock import patch

import backup_talos_install as install

MACHINE = b"""version: v1alpha1
---
kind: RAIDArrayConfig
provisioning:
  volumeSelector:
    match: >-
      "/dev/disk/by-id/first" in disk.symlinks ||
      "/dev/disk/by-id/second" in disk.symlinks
"""
DISK_FIRST = b"spec: {dev_path: /dev/sda, symlinks: [/dev/disk/by-id/first]}"
DISK_SECOND = b"spec: {dev_path: /dev/sdb, symlinks: [/dev/disk/by-id/second]}"
UUID = b"spec: {uuid: 038e1b94-a0f6-11e4-9c0a-9d5496c01100}"


class BackupInstallTargetTests(unittest.TestCase):
    def test_requires_two_separately_discovered_members(self) -> None:
        both = DISK_FIRST + b"\n---\n" + DISK_SECOND
        same = both.replace(b"/dev/sdb", b"/dev/sda")
        for disks, valid in ((both, True), (DISK_FIRST, False), (same, False)):
            with (
                self.subTest(valid=valid, disks=disks),
                patch.object(install, "maintenance_query", side_effect=[UUID, disks]),
            ):
                if valid:
                    install.check_install_target("/talosctl", MACHINE)
                else:
                    with self.assertRaisesRegex(ValueError, "OS disks"):
                        install.check_install_target("/talosctl", MACHINE)

    def test_rejects_unregistered_uuid_before_disk_query(self) -> None:
        with patch.object(
            install, "maintenance_query", return_value=b"spec: {uuid: different}"
        ) as query:
            with self.assertRaisesRegex(ValueError, "KMS registration"):
                install.check_install_target("/talosctl", MACHINE)
        query.assert_called_once_with("/talosctl", "systeminformation")
