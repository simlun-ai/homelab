"""Production boundaries, due-only recovery and native certificate verification."""

import base64
import io
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

import trust_kms_acme_profile as profiles
import trust_kms_acme_record as records
import trust_kms_acme_state as state
import trust_kms_acme_state_operator as operator
import trust_kms_acme_state_remote as remote


class ProductionTests(unittest.TestCase):
    def test_environments_separate_context_format_server_and_paths(self) -> None:
        stage, prod = profiles.profile("staging"), profiles.profile("production")
        for attribute in ("key_id", "format", "server", "directory", "filename"):
            self.assertNotEqual(getattr(stage, attribute), getattr(prod, attribute))
        with self.assertRaises(KeyError):
            profiles.profile("other")
        for environment in ("staging", "production"):
            command = remote.command(
                Path("/example"),
                "test@example.org",
                renew=True,
                environment=environment,
            )
            self.assertEqual(
                command[command.index("--server") + 1],
                profiles.profile(environment).server,
            )
            self.assertEqual("--force-renewal" in command, environment == "staging")
            self.assertIn("--reuse-key", command)
            self.assertIn("--no-random-sleep-on-renew", command)

    def test_cross_environment_snapshots_and_records_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config/dummy").write_bytes(b"public")
            staging = state.snapshot(root)
            with self.assertRaises(ValueError):
                state.restore(root, staging, environment="production")
            encoded = json.dumps(
                {
                    "format": "homelab-wrap-v1",
                    "root_key": "golden-1",
                    "key_id": profiles.profile("staging").key_id,
                    "revision": 1,
                    "salt": base64.b64encode(b"s" * 32).decode(),
                    "nonce": base64.b64encode(b"n" * 12).decode(),
                    "ciphertext": base64.b64encode(b"c" * 32).decode(),
                }
            ).encode()
            records.validate_record(encoded)
            with self.assertRaises(ValueError):
                records.validate_record(encoded, environment="production")

    def test_production_recovery_can_reuse_or_renew_and_preserves_identity(
        self,
    ) -> None:
        for renewed in (False, True):
            with (
                self.subTest(renewed=renewed),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                source, workspace = root / "source", root / "session"
                (source / "config/accounts/example").mkdir(parents=True)
                (source / "config/accounts/example/private_key.json").write_bytes(
                    b"public-fixture"
                )
                (source / "config/renewal").mkdir()
                (source / "config/renewal" / f"{remote.acme.HOSTNAME}.conf").write_text(
                    f"# renew_before_expiry = 30 days\nversion = 4.0.0\narchive_dir = {workspace / 'config/archive'}\n\n[renewalparams]\nserver = {profiles.profile('production').server}\n"
                    f"authenticator = dns-cloudflare\ndns_cloudflare_credentials = {workspace / 'cloudflare.ini'}\n"
                )
                encoded = state.snapshot(source, environment="production")
                request = json.dumps(
                    {
                        "email": "test@example.org",
                        "token": base64.b64encode(b"public-dummy-token").decode(),
                        "state": base64.b64encode(encoded).decode(),
                    }
                ).encode()
                output = io.BytesIO()
                with (
                    patch.object(remote.sys, "argv", ["remote", "production"]),
                    patch.object(remote, "WORKSPACE", workspace),
                    patch.object(remote.acme, "RAM_ROOT", root),
                    patch.object(remote.acme, "require_coordinator_hardening"),
                    patch.object(remote.acme, "require_noswap_mount"),
                    patch.object(
                        remote.acme,
                        "inspect_certificate",
                        side_effect=[
                            (b"old", b"key"),
                            (b"new" if renewed else b"old", b"key"),
                        ],
                    ),
                    patch.object(remote, "verify_production") as verify,
                    patch.object(remote.resource, "setrlimit"),
                    patch.object(remote.os, "umask"),
                    patch.object(remote.sys, "stdin", Mock(buffer=io.BytesIO(request))),
                    patch.object(remote.sys, "stdout", Mock(buffer=output)),
                    patch.object(remote.subprocess, "run") as run,
                    patch("builtins.print"),
                ):
                    self.assertEqual(remote.main(), 0)
                    self.assertNotIn("--force-renewal", run.call_args.args[0])
                    self.assertEqual(verify.call_count, 2)
                    self.assertEqual(output.getvalue(), encoded)
                self.assertFalse(workspace.exists())

    def test_unchanged_production_state_is_not_rewrapped_or_archived(self) -> None:
        fetched = json.dumps(
            {"record": base64.b64encode(b"wrapped-existing").decode()}
        ).encode()
        with (
            patch.object(operator, "require_store", return_value=Path("/example")),
            patch.object(operator, "exchange", return_value=fetched) as exchange,
            patch.object(operator, "crypt", return_value=b"unchanged") as crypt,
            patch.object(
                operator.secrets, "recover_bundle", return_value=b"public-dummy-token"
            ),
            patch.object(operator, "remote", return_value=b"unchanged"),
            patch("builtins.print"),
        ):
            operator.operate(
                "recover",
                "test@example.org",
                "/wrap",
                "/unwrap",
                environment="production",
            )
            self.assertEqual(exchange.call_count, 1)
            self.assertEqual(exchange.call_args.args[0][-1], "production")
            crypt.assert_called_once_with(
                "/unwrap", b"wrapped-existing", wrap=False, environment="production"
            )

    def test_production_record_cannot_overwrite_staging_store(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / records.FILENAME).write_bytes(b"original-staging")
            with (
                patch.object(records, "STORE", root),
                patch.object(
                    records.os,
                    "fstat",
                    return_value=SimpleNamespace(st_uid=0, st_mode=0o40700),
                ),
            ):
                value = {
                    "format": "homelab-wrap-v1",
                    "root_key": "golden-1",
                    "key_id": profiles.profile("production").key_id,
                    "revision": 1,
                    "salt": base64.b64encode(b"s" * 32).decode(),
                    "nonce": base64.b64encode(b"n" * 12).decode(),
                    "ciphertext": base64.b64encode(b"c" * 32).decode(),
                }
                request = json.dumps(
                    {
                        "expected": records.digest(b"original-staging"),
                        "record": base64.b64encode(json.dumps(value).encode()).decode(),
                    }
                ).encode()
                with self.assertRaises(ValueError):
                    records.access("put", request)
                self.assertEqual(
                    (root / records.FILENAME).read_bytes(), b"original-staging"
                )
                self.assertFalse((root / "archive").exists())


class NativeCertificateTests(unittest.TestCase):
    def test_native_trust_hostname_purpose_expiry_and_fullchain_checks(self) -> None:
        now = datetime.now(UTC)
        ca_key = ec.generate_private_key(ec.SECP256R1())
        ca_name = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, "Public test fixture CA")]
        )
        ca = (
            x509.CertificateBuilder()
            .subject_name(ca_name)
            .issuer_name(ca_name)
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=10))
            .not_valid_after(now + timedelta(days=30))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .sign(ca_key, hashes.SHA256())
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lineage = root / "config/live" / remote.acme.HOSTNAME
            lineage.mkdir(parents=True)
            ca_file = root / "test-ca.pem"
            ca_bytes = ca.public_bytes(serialization.Encoding.PEM)
            ca_file.write_bytes(ca_bytes)
            (lineage / "chain.pem").write_bytes(ca_bytes)
            for hostname, expired, server_usage in [
                (remote.acme.HOSTNAME, False, True),
                ("wrong.example.org", False, True),
                (remote.acme.HOSTNAME, True, True),
                (remote.acme.HOSTNAME, False, False),
            ]:
                with self.subTest(
                    hostname=hostname, expired=expired, server_usage=server_usage
                ):
                    key = ec.generate_private_key(ec.SECP256R1())
                    cert = (
                        x509.CertificateBuilder()
                        .subject_name(
                            x509.Name(
                                [x509.NameAttribute(NameOID.COMMON_NAME, hostname)]
                            )
                        )
                        .issuer_name(ca_name)
                        .public_key(key.public_key())
                        .serial_number(x509.random_serial_number())
                        .not_valid_before(now - timedelta(days=2))
                        .not_valid_after(
                            now - timedelta(days=1)
                            if expired
                            else now + timedelta(days=5)
                        )
                        .add_extension(
                            x509.SubjectAlternativeName([x509.DNSName(hostname)]),
                            critical=False,
                        )
                        .add_extension(
                            x509.ExtendedKeyUsage(
                                [
                                    ExtendedKeyUsageOID.SERVER_AUTH
                                    if server_usage
                                    else ExtendedKeyUsageOID.CLIENT_AUTH
                                ]
                            ),
                            critical=False,
                        )
                        .sign(ca_key, hashes.SHA256())
                    )
                    pem = cert.public_bytes(serialization.Encoding.PEM)
                    (lineage / "cert.pem").write_bytes(pem)
                    (lineage / "fullchain.pem").write_bytes(pem + ca_bytes)
                    (lineage / "privkey.pem").write_bytes(
                        key.private_bytes(
                            serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption(),
                        )
                    )
                    if (
                        hostname == remote.acme.HOSTNAME
                        and not expired
                        and server_usage
                    ):
                        remote.verify_production(root, ca_file=ca_file)
                        remote.acme.inspect_certificate(root)
                        with self.assertRaises(remote.acme.RehearsalError):
                            remote.verify_production(
                                root
                            )  # Fixture CA is not system trusted.
                        (lineage / "fullchain.pem").write_bytes(ca_bytes)
                        with self.assertRaises(ValueError):
                            remote.verify_production(root, ca_file=ca_file)
                    else:
                        with self.assertRaises(remote.acme.RehearsalError):
                            remote.verify_production(root, ca_file=ca_file)
                        if expired:
                            remote.verify_production(
                                root, allow_expired=True, ca_file=ca_file
                            )
                            remote.acme.inspect_certificate(root, allow_expired=True)


class RenewalConfigRegressionTests(unittest.TestCase):
    def test_native_configobj_layout_with_lineage_metadata_and_policy_checks(
        self,
    ) -> None:
        # Matches Certbot 4.0.0 storage.write_renewal_config output, including
        # top-level lineage fields that ConfigParser.read() cannot accept.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            filename = root / "config/renewal" / f"{remote.acme.HOSTNAME}.conf"
            filename.parent.mkdir(parents=True)
            for environment in ("staging", "production"):
                with self.subTest(environment=environment):
                    content = (
                        f"# renew_before_expiry = 30 days\nversion = 4.0.0\n"
                        f"archive_dir = {root / 'config/archive'}\n"
                        + "".join(
                            f"{kind} = {root / 'config/live' / remote.acme.HOSTNAME / (kind + '.pem')}\n"
                            for kind in ("cert", "privkey", "chain", "fullchain")
                        )
                        + "\n# Options used in the renewal process\n[renewalparams]\n"
                        + f"server = {profiles.profile(environment).server}\nauthenticator = dns-cloudflare\n"
                        + f"dns_cloudflare_credentials = {root / 'cloudflare.ini'}\n"
                    )
                    filename.write_text(content)
                    remote.check_renewal_config(root, environment)
                    for invalid in (
                        content.replace(
                            profiles.profile(environment).server,
                            "https://wrong.example.org/directory",
                        ),
                        content.replace(
                            "authenticator = dns-cloudflare", "authenticator = manual"
                        ),
                        content.replace(
                            str(root / "cloudflare.ini"), "/wrong/credentials.ini"
                        ),
                        content + "post_hook = echo unsafe\n",
                    ):
                        filename.write_text(invalid)
                        with self.assertRaises(ValueError):
                            remote.check_renewal_config(root, environment)

    def test_post_issuance_failure_reports_safe_stage_and_cleans_ram(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "session"
            request = json.dumps(
                {
                    "email": "test@example.org",
                    "token": base64.b64encode(b"public-dummy-token").decode(),
                    "state": None,
                }
            ).encode()
            output, errors = io.BytesIO(), io.StringIO()
            with (
                patch.object(remote.sys, "argv", ["remote", "production"]),
                patch.object(remote, "WORKSPACE", workspace),
                patch.object(remote.acme, "RAM_ROOT", root),
                patch.object(remote.acme, "require_coordinator_hardening"),
                patch.object(remote.acme, "require_noswap_mount"),
                patch.object(
                    remote.acme, "inspect_certificate", return_value=(b"cert", b"key")
                ),
                patch.object(
                    remote,
                    "check_renewal_config",
                    side_effect=ValueError("private-token-from-parser"),
                ),
                patch.object(remote, "snapshot") as snapshot,
                patch.object(remote, "verify_production") as verify,
                patch.object(remote.resource, "setrlimit"),
                patch.object(remote.os, "umask"),
                patch.object(remote.sys, "stdin", Mock(buffer=io.BytesIO(request))),
                patch.object(remote.sys, "stdout", Mock(buffer=output)),
                patch.object(remote.sys, "stderr", errors),
                patch.object(remote.subprocess, "run"),
            ):
                self.assertEqual(remote.main(), 1)
                snapshot.assert_not_called()
                verify.assert_not_called()
            self.assertIn(
                "failed during checking issued renewal configuration", errors.getvalue()
            )
            self.assertNotIn("private-token-from-parser", errors.getvalue())
            self.assertEqual(output.getvalue(), b"")
            self.assertFalse(workspace.exists())
