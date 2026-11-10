"""State lifecycle regression tests use public dummy payloads only."""

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import trust_kms_acme_state as state
import trust_kms_acme_state_operator as operator


class StateTests(unittest.TestCase):
    def test_snapshot_restores_files_links_and_excludes_dns_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "original"
            (original / "config/archive").mkdir(parents=True)
            (original / "config/live").mkdir()
            (original / "config/archive/cert.pem").write_bytes(b"public-fixture")
            (original / "config/live/cert.pem").symlink_to("../archive/cert.pem")
            (original / "cloudflare.ini").write_bytes(b"dummy-token-outside-config")
            encoded = state.snapshot(original)
            self.assertNotIn(b"dummy-token", encoded)
            recovered = root / "recovered"
            recovered.mkdir()
            state.restore(recovered, encoded)
            self.assertEqual(
                (recovered / "config/live/cert.pem").read_bytes(), b"public-fixture"
            )
            self.assertEqual(state.snapshot(recovered), encoded)

    def test_restore_rejects_escape_and_oversize(self) -> None:
        for name, entry in [
            ("../escape", {"data": ""}),
            ("/absolute", {"data": ""}),
            ("link", {"link": "../../escape"}),
            ("link", {"link": "/etc/passwd"}),
        ]:
            with (
                self.subTest(name=name, entry=entry),
                tempfile.TemporaryDirectory() as directory,
            ):
                encoded = json.dumps(
                    {"format": "trust-acme-staging-v1", "entries": {name: entry}}
                ).encode()
                with self.assertRaises(ValueError):
                    state.restore(Path(directory), encoded)
        with self.assertRaises(ValueError):
            state.restore(Path("/unused"), b"x" * (state.LIMIT + 1))

    def test_publish_archives_exact_old_ciphertext(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record, candidate = root / "current.json", root / "candidate.json"
            record.write_bytes(b"old-ciphertext")
            candidate.write_bytes(b"new-verified-ciphertext")
            operator.publish(record, candidate, b"old-ciphertext")
            self.assertEqual(record.read_bytes(), b"new-verified-ciphertext")
            self.assertEqual(
                [p.read_bytes() for p in (root / "archive").iterdir()],
                [b"old-ciphertext"],
            )

    def test_failed_archive_or_replacement_preserves_current(self) -> None:
        for failure in ("archive", "replacement"):
            with (
                self.subTest(failure=failure),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                record, candidate = root / "current.json", root / "candidate.json"
                record.write_bytes(b"old")
                candidate.write_bytes(b"new")
                if failure == "archive":
                    (root / "archive").symlink_to(root)
                    with self.assertRaises(ValueError):
                        operator.publish(record, candidate, b"old")
                else:
                    with (
                        patch.object(operator.os, "replace", side_effect=OSError()),
                        self.assertRaises(OSError),
                    ):
                        operator.publish(record, candidate, b"old")
                self.assertEqual(record.read_bytes(), b"old")

    def test_modes_fail_closed_and_verified_recreation(self) -> None:
        for mode, existing, succeeds in [
            ("recover", False, False),
            ("init", True, False),
            ("recreate", True, True),
            ("recreate", False, True),
            ("init", False, True),
            ("recover", True, True),
        ]:
            with (
                self.subTest(mode=mode, existing=existing),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                record = root / operator.FILENAME
                if existing:
                    record.write_bytes(b"old")

                def wrap(
                    payload: bytes, _cli: str, *, record: Path, key_id: str
                ) -> None:
                    record.write_bytes(base64.b64encode(payload))

                with (
                    patch.object(operator, "require_store", return_value=root),
                    patch.object(
                        operator.secrets,
                        "recover_bundle",
                        return_value=b"public-dummy-token",
                    ),
                    patch.object(operator.secrets, "wrap_bundle", side_effect=wrap),
                    patch.object(
                        operator, "remote", return_value=b"public-dummy-token"
                    ) as remote,
                    patch("builtins.print"),
                ):
                    if succeeds:
                        operator.operate(mode, "test@example.org", "/wrap", "/unwrap")
                        self.assertEqual(
                            record.read_bytes(), base64.b64encode(b"public-dummy-token")
                        )
                        self.assertEqual((root / "archive").exists(), existing)
                    else:
                        with self.assertRaises(ValueError):
                            operator.operate(
                                mode, "test@example.org", "/wrap", "/unwrap"
                            )
                        remote.assert_not_called()

    def test_failed_issuance_or_verification_never_replaces_record(self) -> None:
        for failure in ("issue", "verify"):
            with (
                self.subTest(failure=failure),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                record = root / operator.FILENAME
                record.write_bytes(b"old")

                def wrap(
                    _payload: bytes, _cli: str, *, record: Path, key_id: str
                ) -> None:
                    record.write_bytes(b"candidate")

                with (
                    patch.object(operator, "require_store", return_value=root),
                    patch.object(
                        operator.secrets,
                        "recover_bundle",
                        return_value=b"public-dummy-token",
                    ),
                    patch.object(operator.secrets, "wrap_bundle", side_effect=wrap),
                    patch.object(
                        operator,
                        "remote",
                        side_effect=ValueError() if failure == "issue" else None,
                        return_value=b"new-state",
                    ),
                    patch("builtins.print"),
                    self.assertRaises(ValueError),
                ):
                    operator.operate("recreate", "test@example.org", "/wrap", "/unwrap")
                self.assertEqual(record.read_bytes(), b"old")
                self.assertFalse((root / "archive").exists())
                self.assertEqual(list(root.glob(".acme-staging-pending-*")), [])


class RemoteStateTests(unittest.TestCase):
    def test_recovered_state_keeps_account_and_cleans_workspace(self) -> None:
        import io
        from unittest.mock import Mock

        import trust_kms_acme_state_remote as remote

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "session"
            source = root / "source"
            (source / "config/accounts/example").mkdir(parents=True)
            (source / "config/accounts/example/private_key.json").write_bytes(
                b"public-account-fixture"
            )
            encoded = state.snapshot(source)
            request = json.dumps(
                {
                    "email": "test@example.org",
                    "token": base64.b64encode(b"public-dummy-token").decode(),
                    "state": base64.b64encode(encoded).decode(),
                }
            ).encode()
            result = io.BytesIO()
            with (
                patch.object(remote, "WORKSPACE", workspace),
                patch.object(remote.acme, "RAM_ROOT", root),
                patch.object(remote.acme, "require_coordinator_hardening"),
                patch.object(remote.acme, "require_noswap_mount"),
                patch.object(
                    remote.acme,
                    "inspect_certificate",
                    side_effect=[(b"old", b"key"), (b"new", b"key")],
                ),
                patch.object(remote.resource, "setrlimit"),
                patch.object(remote.os, "umask"),
                patch.object(remote.sys, "stdin", Mock(buffer=io.BytesIO(request))),
                patch.object(remote.sys, "stdout", Mock(buffer=result)),
                patch.object(remote.subprocess, "run") as run,
                patch("builtins.print"),
            ):
                self.assertEqual(remote.main(), 0)
                self.assertIn("--no-random-sleep-on-renew", run.call_args.args[0])
                self.assertIn("renew", run.call_args.args[0])
            self.assertFalse(workspace.exists())
            self.assertEqual(result.getvalue(), encoded)
