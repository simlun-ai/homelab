"""TLS identity, locked listener and operator-delivery regression checks."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import grpc
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import trust_kms_acme_state_operator as operator  # noqa: E402
import trust_kms_tls_payload as extraction  # noqa: E402
from homelab.trust_kms import control, daemon, session, tls, transport  # noqa: E402


def identity(hostname: str = tls.HOSTNAME) -> tuple[bytes, bytes]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(minutes=10))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ), cert.public_bytes(serialization.Encoding.PEM)


class IdentityTests(unittest.TestCase):
    def test_in_memory_native_verification_rejects_untrusted_mismatch_and_wrong_name(
        self,
    ) -> None:
        key, cert = identity()
        with tempfile.TemporaryDirectory() as directory:
            ca = Path(directory) / "public-ca.pem"
            ca.write_bytes(cert)
            self.assertEqual(
                tls.verified(key, cert + cert, ca_file=ca).subject,
                x509.load_pem_x509_certificate(cert).subject,
            )
            with self.assertRaises(subprocess.CalledProcessError):
                tls.verified(key, cert + cert)  # Not system trusted.
            other_key, wrong_cert = identity("wrong.example.org")
            for bad_key, chain in (
                (other_key, cert + cert),
                (other_key, wrong_cert + wrong_cert),
            ):
                with self.assertRaises(ValueError):
                    tls.verified(bad_key, chain, ca_file=ca)

    def test_snapshot_extraction_is_memory_only_and_rejects_cross_environment_and_escapes(
        self,
    ) -> None:
        key, cert = identity()
        directory = "live/" + tls.HOSTNAME + "/"
        entries = {
            directory + "privkey.pem": {"link": "../../archive/key.pem"},
            "archive/key.pem": {"data": base64.b64encode(key).decode()},
            directory + "fullchain.pem": {"data": base64.b64encode(cert).decode()},
            "accounts/private_key.json": {
                "data": base64.b64encode(b"account-must-not-be-delivered").decode()
            },
        }
        value = {"format": "trust-acme-production-v1", "entries": entries}
        result = extraction.payload(json.dumps(value).encode(), "instance")
        self.assertNotIn(b"account-must-not-be-delivered", result)
        decoded = json.loads(result)
        self.assertEqual(
            set(decoded), {"expected_instance", "private_key", "certificate"}
        )
        self.assertEqual(base64.b64decode(decoded["private_key"]), key)
        self.assertEqual(base64.b64decode(decoded["certificate"]), cert)
        value["format"] = "trust-acme-staging-v1"
        with self.assertRaises(ValueError):
            extraction.payload(json.dumps(value).encode(), "instance")
        value["format"] = "trust-acme-production-v1"
        entries[directory + "privkey.pem"] = {"link": "../../../escape"}
        with self.assertRaises(ValueError):
            extraction.payload(json.dumps(value).encode(), "instance")


class ListenerTests(unittest.TestCase):
    def test_real_locked_rpc_expiry_and_fresh_instance_rejects_old_authorization(
        self,
    ) -> None:
        key, cert = identity()
        with tempfile.TemporaryDirectory() as directory:
            ca = Path(directory) / "ca.pem"
            ca.write_bytes(cert)
            authority = daemon.Authority({})
            listener = tls.Listener(authority, address="127.0.0.1:0", ca_file=ca)
            self.assertEqual(listener.status()["tls_state"], "disabled")
            message: dict[str, object] = {
                "protocol": 1,
                "action": "authorize-tls",
                "expected_instance": authority.status().instance,
                "private_key": base64.b64encode(key).decode(),
                "certificate": base64.b64encode(cert + cert).decode(),
            }
            try:
                with patch.object(tls, "require_memory_policy"):
                    status = listener.dispatch(message)
                self.assertEqual(status["kms_state"], "locked")
                self.assertEqual(status["tls_state"], "active")
                endpoint = status["endpoint"]
                assert isinstance(endpoint, str)
                with grpc.secure_channel(
                    endpoint,
                    grpc.ssl_channel_credentials(cert),
                    options=(("grpc.ssl_target_name_override", tls.HOSTNAME),),
                ) as channel:
                    grpc.channel_ready_future(channel).result(timeout=5)
                    for method in ("Seal", "Unseal"):
                        rpc: grpc.UnaryUnaryMultiCallable[bytes, bytes] = (
                            channel.unary_unary(f"/{transport.SERVICE}/{method}")
                        )
                        with self.assertRaises(grpc.RpcError) as caught:
                            rpc(b"public-test", timeout=5)
                        self.assertEqual(
                            caught.exception.code(), grpc.StatusCode.FAILED_PRECONDITION
                        )
                with self.assertRaises(session.Locked):
                    listener.dispatch(message)
                future = datetime.now(UTC) + timedelta(days=1)
                with patch.object(tls, "datetime", Mock(now=Mock(return_value=future))):
                    self.assertEqual(listener.status()["tls_state"], "disabled")
                self.assertIsNone(listener.status()["fingerprint"])
                fresh = tls.Listener(
                    daemon.Authority({}), address="127.0.0.1:0", ca_file=ca
                )
                with self.assertRaises(session.Locked):
                    fresh.dispatch(message)
                self.assertEqual(fresh.status()["tls_state"], "disabled")
            finally:
                listener.close()

    def test_invalid_identity_does_not_bind(self) -> None:
        authority = daemon.Authority({})
        listener = tls.Listener(authority)
        message: dict[str, object] = {
            "protocol": 1,
            "action": "authorize-tls",
            "expected_instance": authority.status().instance,
            "private_key": base64.b64encode(b"not-a-key").decode(),
            "certificate": base64.b64encode(b"not-a-chain").decode(),
        }
        with (
            patch.object(transport, "listen_tls") as bind,
            self.assertRaises(ValueError),
        ):
            listener.dispatch(message)
        bind.assert_not_called()
        self.assertEqual(listener.status()["tls_state"], "disabled")

    def test_status_peer_denial_and_actual_socket_delivery(self) -> None:
        authority = daemon.Authority({})
        listener = tls.Listener(authority)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tls.sock"
            with control.listen(
                authority,
                path,
                allowed_uids={os.geteuid()},
                handler=listener.dispatch,
                frame_limit=tls.FRAME_LIMIT,
            ):
                self.assertEqual(
                    tls.local("status", socket_path=path)["tls_state"], "disabled"
                )
            with control.listen(
                authority,
                path,
                allowed_uids=set(),
                handler=listener.dispatch,
                frame_limit=tls.FRAME_LIMIT,
            ):
                self.assertEqual(
                    tls.local("status", socket_path=path)["error"], "PERMISSION_DENIED"
                )


class DeliveryTests(unittest.TestCase):
    def test_production_reuse_still_delivers_tls_without_rewrapping(self) -> None:
        fetched = json.dumps({"record": base64.b64encode(b"wrapped").decode()}).encode()
        expected: dict[str, object] = {
            "instance": "instance",
            "tls_state": "disabled",
            "kms_state": "locked",
        }
        with (
            patch.object(operator, "tls_status", return_value=expected),
            patch.object(operator, "require_store", return_value=Path("/example")),
            patch.object(operator, "exchange", return_value=fetched),
            patch.object(operator, "crypt", return_value=b"unchanged") as crypt,
            patch.object(
                operator.secrets, "recover_bundle", return_value=b"public-dummy-token"
            ),
            patch.object(operator, "remote", return_value=b"unchanged"),
            patch.object(operator, "activate_tls") as activate,
            patch("builtins.print"),
        ):
            operator.operate(
                "recover",
                "test@example.org",
                "/wrap",
                "/unwrap",
                environment="production",
                authorize_tls=True,
            )
            activate.assert_called_once_with(b"unchanged", expected)
            self.assertEqual(crypt.call_count, 1)

    def test_active_tls_and_nonproduction_requests_rejected_before_token(self) -> None:
        for environment, mode in (
            ("staging", "recover"),
            ("production", "init"),
            ("production", "recover"),
        ):
            with (
                self.subTest(environment=environment, mode=mode),
                patch.object(
                    operator,
                    "tls_status",
                    return_value={"tls_state": "active", "kms_state": "locked"},
                ),
                patch.object(operator, "require_store") as store,
                self.assertRaises(ValueError),
            ):
                operator.operate(
                    mode,
                    "test@example.org",
                    "/wrap",
                    "/unwrap",
                    environment=environment,
                    authorize_tls=True,
                )
            store.assert_not_called()


class ProcessRestartTests(unittest.TestCase):
    def test_authorized_listener_disappears_on_restart_and_old_epoch_is_rejected(
        self,
    ) -> None:
        key, cert = identity()
        script_directory = Path(__file__).resolve().parents[2] / "scripts"
        # Public disposable CA injection is a test harness API call, never a
        # production CLI switch or environment-variable bypass.
        program = (
            "import sys\nfrom pathlib import Path\nfrom unittest.mock import patch\n"
            "sys.path.insert(0, sys.argv[1])\nimport trust_kms_service as service\n"
            'with patch("homelab.trust_kms.tls.require_memory_policy"):\n'
            '    service.serve_locked(Path(sys.argv[2]), address="127.0.0.1:0", ca_file=Path(sys.argv[3]))\n'
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "tls.sock"
            ca = root / "public-ca.pem"
            ca.write_bytes(cert)
            old_instance: str | None = None
            for iteration in range(2):
                with subprocess.Popen(
                    [
                        sys.executable,
                        "-I",
                        "-B",
                        "-c",
                        program,
                        str(script_directory),
                        str(root / "control.sock"),
                        str(ca),
                    ]
                ) as process:
                    try:
                        deadline = time.monotonic() + 5
                        while (
                            not path.exists()
                            and process.poll() is None
                            and time.monotonic() < deadline
                        ):
                            time.sleep(0.01)
                        self.assertIsNone(process.poll())
                        status = tls.local("status", socket_path=path)
                        self.assertEqual(status["tls_state"], "disabled")
                        self.assertEqual(status["kms_state"], "locked")
                        self.assertNotEqual(status["instance"], old_instance)
                        instance = status["instance"]
                        assert isinstance(instance, str)
                        if iteration == 0:
                            active = tls.local(
                                "authorize-tls",
                                socket_path=path,
                                expected_instance=instance,
                                private_key=base64.b64encode(key).decode(),
                                certificate=base64.b64encode(cert + cert).decode(),
                            )
                            self.assertEqual(active["tls_state"], "active")
                            endpoint = active["endpoint"]
                            assert isinstance(endpoint, str)
                            with grpc.secure_channel(
                                endpoint,
                                grpc.ssl_channel_credentials(cert),
                                options=(
                                    ("grpc.ssl_target_name_override", tls.HOSTNAME),
                                ),
                            ) as channel:
                                grpc.channel_ready_future(channel).result(timeout=5)
                            old_instance = instance
                        else:
                            denied = tls.local(
                                "authorize-tls",
                                socket_path=path,
                                expected_instance=old_instance,
                                private_key=base64.b64encode(key).decode(),
                                certificate=base64.b64encode(cert + cert).decode(),
                            )
                            self.assertEqual(denied["error"], "FAILED_PRECONDITION")
                            self.assertEqual(
                                tls.local("status", socket_path=path)["tls_state"],
                                "disabled",
                            )
                    finally:
                        process.terminate()
                        try:
                            self.assertEqual(process.wait(timeout=10), 0)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            raise
                self.assertFalse(path.exists())


class MemoryPolicyTests(unittest.TestCase):
    def test_only_nonbacked_zram_is_accepted(self) -> None:
        header = "Filename Type Size Used Priority\n"
        cases = [
            ([header], False),
            ([header + "/dev/dm-1 partition 100 0 -2\n"], True),
            ([header + "/dev/zram0 partition 100 0 -2\n", "none\n"], False),
            ([header + "/dev/zram0 partition 100 0 -2\n", "/dev/sda\n"], True),
        ]
        for contents, rejected in cases:
            with (
                self.subTest(contents=contents),
                patch.object(Path, "read_text", side_effect=contents),
            ):
                if rejected:
                    with self.assertRaises(session.Denied):
                        tls.require_memory_policy()
                else:
                    tls.require_memory_policy()

    def test_unsafe_memory_policy_precedes_key_decode_and_binding(self) -> None:
        authority = daemon.Authority({})
        listener = tls.Listener(authority)
        message: dict[str, object] = {
            "protocol": 1,
            "action": "authorize-tls",
            "expected_instance": authority.status().instance,
            "private_key": "not-base64",
            "certificate": "not-base64",
        }
        with (
            patch.object(tls, "require_memory_policy", side_effect=session.Denied()),
            patch.object(tls, "verified") as verify,
            patch.object(transport, "listen_tls") as bind,
            self.assertRaises(session.Denied),
        ):
            listener.dispatch(message)
        verify.assert_not_called()
        bind.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
