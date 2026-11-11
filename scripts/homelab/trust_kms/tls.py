"""Process-lifetime TLS identity; independent of the locked KMS key authority."""

from __future__ import annotations

import base64
import ctypes
import os
import re
import resource
import socket
import subprocess
import threading
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

from . import control, daemon, envelope, session, transport

HOSTNAME = "kms.k8s-aux.simlun.se"
ADDRESS = "10.10.0.5:443"
SOCKET = Path("/run/trust-kms/tls.sock")
FRAME_LIMIT = 64 * 1024
CA_FILE = Path("/etc/ssl/certs/ca-certificates.crt")


def harden_process() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if ctypes.CDLL(None, use_errno=True).prctl(4, 0, 0, 0, 0) != 0:
        raise ValueError("Cannot disable process dumping")


def require_memory_policy() -> None:
    for line in Path("/proc/swaps").read_text().splitlines()[1:]:
        device = line.split()[0]
        if not re.fullmatch(r"/dev/zram[0-9]+", device):
            raise session.Denied()
        if (
            Path("/sys/block") / Path(device).name / "backing_dev"
        ).read_text().strip() != "none":
            raise session.Denied()


def verified(key: bytes, chain: bytes, *, ca_file: Path = CA_FILE) -> x509.Certificate:
    if not 0 < len(key) <= 8192 or not 0 < len(chain) <= 16384:
        raise envelope.InvalidArgument()
    certificates = x509.load_pem_x509_certificates(chain)
    if not certificates:
        raise envelope.InvalidArgument()
    leaf = certificates[0]
    private = serialization.load_pem_private_key(key, password=None)
    public = leaf.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    if (
        private.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        != public
    ):
        raise envelope.InvalidArgument()
    if leaf.extensions.get_extension_for_class(
        x509.SubjectAlternativeName
    ).value.get_values_for_type(x509.DNSName) != [HOSTNAME]:
        raise envelope.InvalidArgument()
    now = datetime.now(UTC)
    if not leaf.not_valid_before_utc <= now < leaf.not_valid_after_utc:
        raise envelope.InvalidArgument()
    # OpenSSL receives only anonymous RAM descriptors. No named key/cert files
    # are created by the daemon, and the private key never reaches OpenSSL.
    descriptors: list[int] = []
    try:
        for content in (
            leaf.public_bytes(serialization.Encoding.PEM),
            b"".join(
                cert.public_bytes(serialization.Encoding.PEM)
                for cert in certificates[1:]
            ),
        ):
            fd = os.memfd_create("kms-public-cert", os.MFD_CLOEXEC)
            descriptors.append(fd)
            os.write(fd, content)
            os.lseek(fd, 0, os.SEEK_SET)
        subprocess.run(
            [
                "/usr/bin/openssl",
                "verify",
                "-CAfile",
                str(ca_file),
                "-no-CApath",
                "-no-CAstore",
                "-purpose",
                "sslserver",
                "-verify_hostname",
                HOSTNAME,
                "-untrusted",
                f"/proc/self/fd/{descriptors[1]}",
                f"/proc/self/fd/{descriptors[0]}",
            ],
            pass_fds=tuple(descriptors),
            env={"PATH": "/usr/bin:/bin", "OPENSSL_CONF": "/dev/null"},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=15,
        )
    finally:
        for fd in descriptors:
            os.close(fd)
    return leaf


class Listener:
    def __init__(
        self,
        authority: daemon.Authority,
        *,
        address: str = ADDRESS,
        ca_file: Path = CA_FILE,
    ) -> None:
        self.authority = authority
        self.address = address
        self.ca_file = ca_file
        self._mutex = threading.RLock()
        self._stack: ExitStack | None = None
        self._not_before: datetime | None = None
        self._expiry: datetime | None = None
        self._fingerprint: str | None = None
        self._endpoint: str | None = None

    def close(self) -> None:
        with self._mutex:
            if self._stack is not None:
                self._stack.close()
            self._stack = None
            self._not_before = None
            self._expiry = None
            self._fingerprint = None
            self._endpoint = None

    def expire(self) -> None:
        with self._mutex:
            now = datetime.now(UTC)
            if self._expiry is not None and (
                now >= self._expiry
                or (self._not_before is not None and now < self._not_before)
            ):
                self.close()

    def status(self) -> dict[str, object]:
        with self._mutex:
            self.expire()
            status = self.authority.status()
            return {
                "protocol": 1,
                "instance": status.instance,
                "kms_state": status.state,
                "tls_state": "active" if self._stack is not None else "disabled",
                "endpoint": self._endpoint,
                "fingerprint": self._fingerprint,
                "cert_not_after": None
                if self._expiry is None
                else self._expiry.isoformat(),
            }

    def dispatch(self, message: dict[str, object]) -> dict[str, object]:
        with self._mutex:
            if type(message.get("protocol")) is not int or message["protocol"] != 1:
                raise envelope.InvalidArgument()
            if message == {"protocol": 1, "action": "status"}:
                return self.status()
            if (
                message.keys()
                != {
                    "protocol",
                    "action",
                    "expected_instance",
                    "private_key",
                    "certificate",
                }
                or message["action"] != "authorize-tls"
            ):
                raise envelope.InvalidArgument()
            self.expire()
            if (
                self._stack is not None
                or self.authority.status().state != "locked"
                or envelope.node_uuid(message["expected_instance"])
                != self.authority.status().instance
            ):
                raise session.Locked()
            require_memory_policy()
            raw_key, raw_chain = message["private_key"], message["certificate"]
            if not isinstance(raw_key, str) or not isinstance(raw_chain, str):
                raise envelope.InvalidArgument()
            key = base64.b64decode(raw_key, validate=True)
            chain = base64.b64decode(raw_chain, validate=True)
            leaf = verified(key, chain, ca_file=self.ca_file)
            stack = ExitStack()
            try:
                endpoint = stack.enter_context(
                    transport.listen_tls(
                        self.authority,
                        private_key=key,
                        certificate=chain,
                        address=self.address,
                    )
                )
            except Exception:
                stack.close()
                raise
            self._stack = stack
            self._endpoint = endpoint
            self._not_before = leaf.not_valid_before_utc
            self._expiry = leaf.not_valid_after_utc
            self._fingerprint = leaf.fingerprint(hashes.SHA256()).hex()
            return self.status()


def local(
    action: str, *, socket_path: Path = SOCKET, **fields: object
) -> dict[str, object]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
        peer.connect(str(socket_path))
        control.send(
            peer, {"protocol": 1, "action": action, **fields}, frame_limit=FRAME_LIMIT
        )
        return control.receive(peer, frame_limit=FRAME_LIMIT, timeout=20)
