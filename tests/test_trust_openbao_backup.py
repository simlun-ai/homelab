"""Verify the backup workflow's credential and restore-target boundaries."""

import json
import unittest
from typing import cast
from unittest.mock import patch

import yaml

import trust_openbao_backup as backup


class TrustOpenBaoBackupTests(unittest.TestCase):
    def test_scheduled_job_separates_credentials_from_restore(self) -> None:
        cron = cast(
            backup.Object, list(yaml.safe_load_all(backup.RESOURCES.read_text()))[-1]
        )
        schedule = cron["spec"]
        pod = schedule["jobTemplate"]["spec"]["template"]["spec"]
        stages = {container["name"]: container for container in pod["initContainers"]}

        def mounts(container: backup.Object) -> set[str]:
            return {mount["name"] for mount in container["volumeMounts"]}

        self.assertEqual(schedule["concurrencyPolicy"], "Forbid")
        self.assertTrue(schedule["suspend"])
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertIn("writer", mounts(stages["backup"]))
        self.assertIn("identity", mounts(stages["backup"]))
        self.assertIn("reader", mounts(stages["download"]))
        self.assertEqual(mounts(pod["containers"][0]), {"pipeline", "tools", "work"})
        self.assertEqual(pod["containers"][0]["args"], ["restore"])

    def test_manual_restore_job_uses_only_read_only_repository_credentials(
        self,
    ) -> None:
        cron = cast(
            backup.Object, list(yaml.safe_load_all(backup.RESOURCES.read_text()))[-1]
        )
        with patch.object(backup, "Kubernetes", autospec=True) as kubernetes:
            kube = kubernetes.return_value
            kube.get.return_value = cron
            backup.private_job(kube, "verify", "a" * 64)
            job = json.loads(kube.run.call_args.kwargs["data"])
        pod = job["spec"]["template"]["spec"]
        self.assertEqual(
            [stage["name"] for stage in pod["initContainers"]],
            ["stage-bao", "stage-restic", "download"],
        )
        self.assertEqual(pod["containers"][0]["args"], ["restore-hold"])
        self.assertEqual(
            {v["name"] for v in pod["volumes"]},
            {"pipeline", "tools", "work", "reader"},
        )
        self.assertEqual(
            pod["initContainers"][-1]["env"],
            [{"name": "RESTORE_SNAPSHOT_ID", "value": "a" * 64}],
        )
