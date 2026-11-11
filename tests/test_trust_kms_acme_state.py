"""State lifecycle regression tests use public dummy payloads only."""

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import trust_kms_acme_record as records
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
            records.publish(record, candidate, b"old-ciphertext")
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
                        records.publish(record, candidate, b"old")
                else:
                    with (
                        patch.object(records.os, "replace", side_effect=OSError()),
                        self.assertRaises(OSError),
                    ):
                        records.publish(record, candidate, b"old")
                self.assertEqual(record.read_bytes(), b"old")

    def test_modes_use_coordinator_state_and_never_write_private_checkout(self) -> None:
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
                previous = b"old" if existing else None
                fetched = json.dumps(
                    {
                        "record": None
                        if previous is None
                        else base64.b64encode(previous).decode()
                    }
                ).encode()

                def crypt(
                    _tool: str,
                    _data: bytes,
                    *,
                    wrap: bool,
                    environment: str = "staging",
                ) -> bytes:
                    return b"wrapped" if wrap else b"new-state"

                with (
                    patch.object(operator, "require_store", return_value=root),
                    patch.object(
                        operator.secrets,
                        "recover_bundle",
                        return_value=b"public-dummy-token",
                    ),
                    patch.object(
                        operator,
                        "crypt",
                        side_effect=crypt,
                    ),
                    patch.object(
                        operator, "exchange", side_effect=[fetched, b"ok\n"]
                    ) as exchange,
                    patch.object(
                        operator, "remote", return_value=b"new-state"
                    ) as remote,
                    patch("builtins.print"),
                ):
                    if succeeds:
                        operator.operate(mode, "test@example.org", "/wrap", "/unwrap")
                        request = json.loads(exchange.call_args.args[1])
                        self.assertEqual(request["expected"], records.digest(previous))
                        self.assertEqual(
                            base64.b64decode(request["record"]), b"wrapped"
                        )
                    else:
                        with self.assertRaises(ValueError):
                            operator.operate(
                                mode, "test@example.org", "/wrap", "/unwrap"
                            )
                        remote.assert_not_called()
                self.assertEqual(list(root.iterdir()), [])

    def test_failed_issuance_or_verification_never_publishes(self) -> None:
        for failure in ("issue", "verify"):
            with (
                self.subTest(failure=failure),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                fetched = json.dumps(
                    {"record": base64.b64encode(b"old").decode()}
                ).encode()
                with (
                    patch.object(operator, "require_store", return_value=root),
                    patch.object(
                        operator.secrets,
                        "recover_bundle",
                        return_value=b"public-dummy-token",
                    ),
                    patch.object(
                        operator, "crypt", side_effect=[b"wrapped", b"wrong-plaintext"]
                    ),
                    patch.object(
                        operator, "exchange", return_value=fetched
                    ) as exchange,
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
                self.assertEqual(exchange.call_count, 1)
                self.assertEqual(list(root.iterdir()), [])

    def test_import_verifies_and_uploads_without_issuance_or_deleting_source(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "old.json"
            source.write_bytes(b"wrapped-existing")
            with (
                patch.object(operator, "require_store", return_value=root),
                patch.object(
                    operator,
                    "crypt",
                    return_value=b'{"format":"trust-acme-staging-v1"}',
                ) as crypt,
                patch.object(
                    operator, "exchange", side_effect=[b'{"record":null}', b"ok\n"]
                ) as exchange,
                patch.object(operator, "remote") as remote,
                patch.object(operator.secrets, "recover_bundle") as dns,
                patch("builtins.print"),
            ):
                operator.operate(
                    "import", "test@example.org", "/wrap", "/unwrap", source
                )
                crypt.assert_called_once_with(
                    "/unwrap", b"wrapped-existing", wrap=False, environment="staging"
                )
                remote.assert_not_called()
                dns.assert_not_called()
                self.assertEqual(
                    base64.b64decode(json.loads(exchange.call_args.args[1])["record"]),
                    source.read_bytes(),
                )
            self.assertEqual(source.read_bytes(), b"wrapped-existing")


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
            (source / "config/renewal").mkdir()
            (source / "config/renewal" / f"{remote.acme.HOSTNAME}.conf").write_text(
                f"[renewalparams]\nserver = {remote.acme.STAGING_CA}\nauthenticator = dns-cloudflare\n"
                f"dns_cloudflare_credentials = {workspace / 'cloudflare.ini'}\n"
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
                patch.object(remote.sys, "argv", ["state-remote"]),
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


class CoordinatorRecordTests(unittest.TestCase):
    def fixture(self) -> bytes:
        return json.dumps(
            {
                "format": "homelab-wrap-v1",
                "root_key": "golden-1",
                "key_id": records.KEY_ID,
                "revision": 1,
                "salt": base64.b64encode(b"s" * 32).decode(),
                "nonce": base64.b64encode(b"n" * 12).decode(),
                "ciphertext": base64.b64encode(b"public-test-data" * 2).decode(),
            }
        ).encode()

    def test_compare_and_replace_rejects_stale_workstation_and_archives(self) -> None:
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch.object(records, "STORE", root),
                patch.object(
                    records.os,
                    "fstat",
                    return_value=SimpleNamespace(st_uid=0, st_mode=0o40700),
                ),
            ):
                self.assertIsNone(json.loads(records.access("get", b""))["record"])
                first = self.fixture()
                request = json.dumps(
                    {"expected": None, "record": base64.b64encode(first).decode()}
                ).encode()
                self.assertEqual(records.access("put", request), b"ok\n")
                self.assertEqual(
                    base64.b64decode(json.loads(records.access("get", b""))["record"]),
                    first,
                )
                second = first + b"\n"
                update = json.dumps(
                    {
                        "expected": records.digest(first),
                        "record": base64.b64encode(second).decode(),
                    }
                ).encode()
                self.assertEqual(records.access("put", update), b"ok\n")
                with self.assertRaises(ValueError):
                    records.access("put", update)
                self.assertEqual((root / records.FILENAME).read_bytes(), second)
                self.assertEqual(
                    [p.read_bytes() for p in (root / "archive").iterdir()], [first]
                )
                self.assertEqual(list(root.glob(".pending-*")), [])

    def test_corrupt_empty_record_is_distinct_from_missing(self) -> None:
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / records.FILENAME).write_bytes(b"")
            with (
                patch.object(records, "STORE", root),
                patch.object(
                    records.os,
                    "fstat",
                    return_value=SimpleNamespace(st_uid=0, st_mode=0o40700),
                ),
            ):
                self.assertEqual(json.loads(records.access("get", b""))["record"], "")
                request = json.dumps(
                    {
                        "expected": None,
                        "record": base64.b64encode(self.fixture()).decode(),
                    }
                ).encode()
                with self.assertRaises(ValueError):
                    records.access("put", request)

    def test_persistence_rejects_plaintext_wrong_context_and_directory_links(
        self,
    ) -> None:
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for data in (
                b"plaintext",
                self.fixture().replace(b"golden-1", b"wrong-root"),
            ):
                with (
                    patch.object(records, "STORE", root),
                    patch.object(
                        records.os,
                        "fstat",
                        return_value=SimpleNamespace(st_uid=0, st_mode=0o40700),
                    ),
                    self.assertRaises(ValueError),
                ):
                    records.access(
                        "put",
                        json.dumps(
                            {
                                "expected": None,
                                "record": base64.b64encode(data).decode(),
                            }
                        ).encode(),
                    )
            self.assertEqual(list(root.iterdir()), [])
            link = root / "link"
            link.symlink_to(root, target_is_directory=True)
            with patch.object(records, "STORE", link), self.assertRaises(OSError):
                records.access("get", b"")
