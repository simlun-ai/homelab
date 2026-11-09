"""Exercise the pinned Talos KMS wire contract over local, verified TLS."""

from __future__ import annotations

import ipaddress
import os
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
import unittest
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import grpc
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from homelab.trust_kms import control, daemon, envelope, session, transport  # noqa: E402

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
    def test_revoke_before_response_handoff(self) -> None:
        entered, resume = threading.Event(), threading.Event()

        class DelayedSession(session.Session):
            def release(self, epoch: str | None, data: bytes) -> bytes:
                if data == b"\x0a\x20" + PUBLIC_PAYLOAD:
                    entered.set()
                    if not resume.wait(5):
                        raise TimeoutError()
                return super().release(epoch, data)

        authority = DelayedSession({NODE: session.Policy(frozenset({KEY_ID}), KEY_ID)})
        authority.activate(
            authority.status().instance,
            str(uuid4()),
            [session.Grant(NODE, KEY_ID, PUBLIC_TEST_KEY)],
        )
        sealed = authority.seal(NODE, PUBLIC_PAYLOAD)
        key, cert = disposable_tls()
        with (
            transport.listen_loopback(
                authority, private_key=key, certificate=cert
            ) as endpoint,
            grpc.secure_channel(
                endpoint, grpc.ssl_channel_credentials(cert)
            ) as channel,
        ):
            unseal: grpc.UnaryUnaryMultiCallable[bytes, bytes] = channel.unary_unary(
                "/sidero.kms.KMSService/Unseal"
            )
            pending = unseal.future(request(sealed), timeout=10)
            try:
                self.assertTrue(entered.wait(5))
                authority.lock()
            finally:
                resume.set()
            with self.assertRaises(grpc.RpcError) as caught:
                pending.result()
            # gRPC maps a rejected response serializer to INTERNAL.
            self.assertEqual(caught.exception.code(), grpc.StatusCode.INTERNAL)

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


def local(path: Path, action: str, **fields: object) -> dict[str, object]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
        peer.connect(str(path))
        control.send(peer, {"protocol": 1, "action": action, **fields})
        return control.receive(peer)


def wait_until(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 5
    while not condition():
        if time.monotonic() >= deadline:
            raise AssertionError("KMS rehearsal condition timed out")
        time.sleep(0.01)


class DaemonRehearsal(unittest.TestCase):
    def test_local_authorization_and_worker_lifecycle(self) -> None:
        now = 0.0
        policy = {NODE: session.Policy(frozenset({KEY_ID}), KEY_ID)}
        authority = daemon.Authority(policy, clock=lambda: now)
        key, cert = disposable_tls()
        wire = request(PUBLIC_PAYLOAD)

        with TemporaryDirectory(prefix="trust-kms-") as directory:
            path = Path(directory) / "control.sock"
            with (
                authority.run(),
                control.listen(authority, path, allowed_uids={os.geteuid()}),
                transport.listen_loopback(
                    authority, private_key=key, certificate=cert
                ) as endpoint,
                grpc.secure_channel(
                    endpoint, grpc.ssl_channel_credentials(cert)
                ) as channel,
            ):
                seal: grpc.UnaryUnaryMultiCallable[bytes, bytes] = channel.unary_unary(
                    "/sidero.kms.KMSService/Seal"
                )
                unseal: grpc.UnaryUnaryMultiCallable[bytes, bytes] = (
                    channel.unary_unary("/sidero.kms.KMSService/Unseal")
                )
                initial = local(path, "status")
                self.assertEqual(initial["state"], "locked")
                fields: dict[str, object] = {
                    "expected_instance": initial["instance"],
                    "grants": [
                        {
                            "node_uuid": NODE,
                            "key_id": KEY_ID,
                            "key": envelope.b64(PUBLIC_TEST_KEY),
                        }
                    ],
                }

                def activate() -> dict[str, object]:
                    return local(
                        path, "open-boot-window", request_id=str(uuid4()), **fields
                    )

                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
                    peer.connect(str(path))
                    peer.sendall(struct.pack("!I", control.FRAME_LIMIT + 1))
                    self.assertEqual(control.receive(peer)["error"], "INVALID_ARGUMENT")

                active = activate()
                self.assertEqual(active["state"], "active")
                self.assertEqual(
                    local(path, "open-boot-window", request_id=str(uuid4()), **fields)[
                        "error"
                    ],
                    "FAILED_PRECONDITION",
                )
                sealed_data = transport.RESPONSE.FromString(seal(wire, timeout=5)).data
                self.assertEqual(
                    transport.RESPONSE.FromString(
                        unseal(request(sealed_data), timeout=5)
                    ).data,
                    PUBLIC_PAYLOAD,
                )

                current = authority.worker
                assert current is not None and current.process.pid is not None
                pid = current.process.pid
                os.kill(pid, signal.SIGSTOP)
                pending = unseal.future(request(sealed_data), timeout=5)
                wait_until(current.io.locked)
                self.assertEqual(local(path, "lock-KMS")["state"], "locked")
                self.assertFalse(Path(f"/proc/{pid}").exists())
                with self.assertRaises(grpc.RpcError) as caught:
                    pending.result()
                self.assertEqual(
                    caught.exception.code(), grpc.StatusCode.FAILED_PRECONDITION
                )
                self.assertEqual(
                    local(
                        path,
                        "open-boot-window",
                        request_id=active["request_id"],
                        **fields,
                    )["error"],
                    "FAILED_PRECONDITION",
                )

                self.assertEqual(activate()["state"], "active")
                current = authority.worker
                assert current is not None and current.process.pid is not None
                process = Path(f"/proc/{current.process.pid}")
                now += session.WINDOW_SECONDS
                # Observe reaping before calling any status or RPC that could expire it.
                wait_until(lambda: not process.exists())
                self.assertEqual(local(path, "status")["state"], "locked")

                self.assertEqual(activate()["state"], "active")
                current = authority.worker
                assert current is not None and current.process.pid is not None
                pid = current.process.pid
                os.kill(pid, signal.SIGKILL)
                wait_until(lambda: not Path(f"/proc/{pid}").exists())
                self.assertEqual(local(path, "status")["state"], "locked")

            replacement = daemon.Authority(policy)
            with (
                replacement.run(),
                control.listen(replacement, path, allowed_uids={os.geteuid()}),
            ):
                self.assertEqual(local(path, "status")["state"], "locked")
                self.assertEqual(
                    local(path, "open-boot-window", request_id=str(uuid4()), **fields)[
                        "error"
                    ],
                    "PERMISSION_DENIED",
                )

            with control.listen(replacement, path, allowed_uids=set()):
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
                    peer.connect(str(path))
                    self.assertEqual(
                        control.receive(peer)["error"], "PERMISSION_DENIED"
                    )


class StagingServiceRehearsal(unittest.TestCase):
    def test_locked_service_starts_and_restarts_without_tls(self) -> None:
        script = Path(__file__).resolve().parents[2] / "scripts/trust_kms_service.py"
        command = [sys.executable, "-I", "-B", str(script)]
        with TemporaryDirectory(prefix="trust-kms-stage-") as directory:
            path = Path(directory) / "control.sock"
            previous: object = None
            for _ in range(2):
                with subprocess.Popen(
                    [*command, "serve-locked", "--socket", str(path)]
                ) as process:
                    try:

                        def ready() -> bool:
                            return (
                                path.exists()
                                and subprocess.run(
                                    [*command, "status", "--socket", str(path)],
                                    check=False,
                                    timeout=5,
                                    capture_output=True,
                                ).returncode
                                == 0
                            )

                        wait_until(lambda: process.poll() is not None or ready())
                        self.assertIsNone(process.poll())
                        status = local(path, "status")
                        instance = status["instance"]
                        self.assertNotEqual(instance, previous)
                        previous = instance
                        self.assertEqual(
                            local(
                                path,
                                "open-boot-window",
                                expected_instance=instance,
                                request_id=str(uuid4()),
                                grants=[
                                    {
                                        "node_uuid": NODE,
                                        "key_id": KEY_ID,
                                        "key": envelope.b64(PUBLIC_TEST_KEY),
                                    }
                                ],
                            )["error"],
                            "PERMISSION_DENIED",
                        )
                    finally:
                        process.terminate()
                        try:
                            self.assertEqual(process.wait(timeout=5), 0)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            raise
                self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
