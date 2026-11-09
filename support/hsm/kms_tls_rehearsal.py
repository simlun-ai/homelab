"""Exercise the pinned Talos KMS wire contract over local, verified TLS."""

from __future__ import annotations

import ipaddress
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import grpc
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from homelab.trust_kms import session, transport  # noqa: E402

NODE = "11111111-1111-4111-8111-111111111111"
UNKNOWN_NODE = "22222222-2222-4222-8222-222222222222"
KEY_ID = "homelab/v1/trust/kms/disposable/r1"
PUBLIC_TEST_KEY = b"k" * 32
PUBLIC_PAYLOAD = b"p" * 32


def disposable_tls() -> tuple[bytes, bytes]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Trust KMS rehearsal")])
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
            x509.SubjectAlternativeName(
                [x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))]
            ),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    return (
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
        cert.public_bytes(serialization.Encoding.PEM),
    )


def request(data: bytes, *, node: str = NODE) -> bytes:
    message = transport.REQUEST()
    message.node_uuid = node
    message.data = data
    return message.SerializeToString()


class TLSRehearsal(unittest.TestCase):
    def test_window_over_tls(self) -> None:
        now = 0.0
        authority = session.Session(
            {NODE: session.Policy(frozenset({KEY_ID}), KEY_ID)}, clock=lambda: now
        )

        def activate() -> None:
            authority.activate(
                authority.status().instance,
                str(uuid4()),
                [session.Grant(NODE, KEY_ID, PUBLIC_TEST_KEY)],
            )

        key, cert = disposable_tls()
        with transport.listen_loopback(
            authority, private_key=key, certificate=cert
        ) as endpoint:
            with grpc.secure_channel(
                endpoint, grpc.ssl_channel_credentials(cert)
            ) as channel:
                grpc.channel_ready_future(channel).result(timeout=5)
                seal: grpc.UnaryUnaryMultiCallable[bytes, bytes] = channel.unary_unary(
                    "/sidero.kms.KMSService/Seal"
                )
                unseal: grpc.UnaryUnaryMultiCallable[bytes, bytes] = (
                    channel.unary_unary("/sidero.kms.KMSService/Unseal")
                )
                # Fixed wire fixtures independently pin the field numbers and types.
                wire = b"\x0a\x24" + NODE.encode("ascii") + b"\x12\x20" + PUBLIC_PAYLOAD
                self.assertEqual(wire, request(PUBLIC_PAYLOAD))
                self.assert_rpc_error(grpc.StatusCode.FAILED_PRECONDITION, seal, wire)

                activate()
                sealed = transport.RESPONSE.FromString(seal(wire, timeout=5))
                sealed_data = sealed.data
                self.assertIsInstance(sealed_data, bytes)
                self.assertEqual(
                    unseal(request(sealed_data), timeout=5),
                    b"\x0a\x20" + PUBLIC_PAYLOAD,
                )
                self.assert_rpc_error(
                    grpc.StatusCode.PERMISSION_DENIED,
                    seal,
                    request(PUBLIC_PAYLOAD, node=UNKNOWN_NODE),
                )
                self.assert_rpc_error(grpc.StatusCode.INVALID_ARGUMENT, seal, b"\x0a")
                self.assert_rpc_error(
                    grpc.StatusCode.INVALID_ARGUMENT, seal, request(b"short")
                )
                self.assert_rpc_error(
                    grpc.StatusCode.RESOURCE_EXHAUSTED,
                    seal,
                    b"x" * (transport.MAX_MESSAGE_BYTES + 1),
                )

                now += session.WINDOW_SECONDS
                self.assert_rpc_error(
                    grpc.StatusCode.FAILED_PRECONDITION, unseal, request(sealed_data)
                )
                activate()
                authority.lock()
                self.assert_rpc_error(grpc.StatusCode.FAILED_PRECONDITION, seal, wire)

            with grpc.secure_channel(
                endpoint, grpc.ssl_channel_credentials()
            ) as channel:
                untrusted_seal: grpc.UnaryUnaryMultiCallable[bytes, bytes] = (
                    channel.unary_unary("/sidero.kms.KMSService/Seal")
                )
                self.assert_rpc_error(grpc.StatusCode.UNAVAILABLE, untrusted_seal, wire)

    def assert_rpc_error(
        self,
        expected: grpc.StatusCode,
        rpc: grpc.UnaryUnaryMultiCallable[bytes, bytes],
        data: bytes,
    ) -> None:
        with self.assertRaises(grpc.RpcError) as caught:
            rpc(data, timeout=5)
        self.assertEqual(caught.exception.code(), expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
