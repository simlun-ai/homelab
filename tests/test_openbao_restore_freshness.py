"""Enforce the scheduled restore's freshness boundary."""

import subprocess
import unittest
from pathlib import Path

FRESHNESS = (
    Path(__file__).resolve().parents[1]
    / "clusters/trust/helm/charts/openbao-jobs/scripts/freshness.sh"
)


class OpenBaoRestoreFreshnessTests(unittest.TestCase):
    def test_rejects_invalid_future_and_at_least_24_hour_old_snapshots(self) -> None:
        now = "1795386400"
        for created, expected in (
            ("1795300001", 0),
            ("1795300000", 1),
            ("1795299999", 1),
            ("1795386401", 1),
            ("", 1),
            ("invalid", 1),
        ):
            with self.subTest(created=created):
                result = subprocess.run(
                    [
                        "/bin/sh",
                        "-c",
                        '. "$1"; check_freshness "$2" "$3"',
                        "restore-test",
                        str(FRESHNESS),
                        created,
                        now,
                    ],
                    check=False,
                    capture_output=True,
                    timeout=5,
                )
                self.assertEqual(result.returncode, expected)
