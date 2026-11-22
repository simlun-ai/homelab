"""Talos KMS RPCs backed by one cluster's OpenBao Transit key."""

import base64
import json
import re
import ssl
from collections.abc import Callable, Generator, Iterable
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from http.client import HTTPException, HTTPSConnection
from threading import Lock
from urllib.parse import urlsplit
from uuid import UUID

import grpc
from google.protobuf.message import DecodeError

from .talos_kms_wire import MAX_MESSAGE_BYTES, REQUEST, RESPONSE, SERVICE

_PAYLOAD_PREFIX = b"homelab-talos-kms-v1:"
_CIPHERTEXT = re.compile(rb"vault:v[1-9][0-9]*:[A-Za-z0-9+/]+={0,2}")
_UNLOCK_BYTES = 32
_TRANSIT_TIMEOUT = 4
_MAX_INFLIGHT = 8


class TransitUnavailable(RuntimeError):
    """OpenBao did not complete the requested operation."""


class TransitKMS:
    def __init__(
        self,
        endpoint: str,
        key: str,
        nodes: Iterable[str],
        token: Callable[[], str],
        *,
        tls: ssl.SSLContext | None = None,
    ) -> None:
        url = urlsplit(endpoint)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username is not None
            or url.path not in ("", "/")
            or url.query
            or url.fragment
        ):
            raise ValueError("OpenBao endpoint must be an HTTPS origin")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", key):
            raise ValueError("Invalid Transit key name")
        self._nodes = frozenset(nodes)
        if not self._nodes or any(str(UUID(node)) != node for node in self._nodes):
            raise ValueError("Configure at least one canonical Talos node UUID")
        self._host = url.hostname
        self._port = url.port
        self._key = key
        self._token = token
        self._tls = tls if tls is not None else ssl.create_default_context()
        if not self._tls.check_hostname or self._tls.verify_mode != ssl.CERT_REQUIRED:
            raise ValueError("OpenBao TLS must verify the certificate and hostname")

    def _call(self, operation: str, field: str, value: str, node: str) -> str:
        associated_data = base64.b64encode(_PAYLOAD_PREFIX + node.encode()).decode()
        body = json.dumps({field: value, "associated_data": associated_data})
        try:
            with closing(
                HTTPSConnection(
                    self._host, self._port, timeout=_TRANSIT_TIMEOUT, context=self._tls
                )
            ) as connection:
                connection.request(
                    "POST",
                    f"/v1/transit/{operation}/{self._key}",
                    body,
                    {
                        "Content-Type": "application/json",
                        "X-Vault-Token": self._token(),
                    },
                )
                response = connection.getresponse()
                if response.status != 200:
                    raise TransitUnavailable("OpenBao Transit rejected the request")
                raw = response.read(MAX_MESSAGE_BYTES + 1)
                if len(raw) > MAX_MESSAGE_BYTES:
                    raise TransitUnavailable("Oversized OpenBao Transit response")
                result: object = json.loads(raw)
        except (OSError, HTTPException, ValueError):
            raise TransitUnavailable("OpenBao Transit request failed") from None
        match result:
            case {"data": {"ciphertext": str() as ciphertext}} if (
                operation == "encrypt"
            ):
                return ciphertext
            case {"data": {"plaintext": str() as plaintext}} if operation == "decrypt":
                return plaintext
            case _:
                raise TransitUnavailable("Invalid OpenBao Transit response")

    def seal(self, node: str, data: bytes) -> bytes:
        if node not in self._nodes:
            raise PermissionError("Unknown Talos node")
        if len(data) != _UNLOCK_BYTES:
            raise ValueError("Invalid Talos unlock length")
        plaintext = base64.b64encode(data).decode()
        ciphertext = self._call("encrypt", "plaintext", plaintext, node).encode()
        if not _CIPHERTEXT.fullmatch(ciphertext):
            raise TransitUnavailable("Invalid Transit ciphertext response")
        return _PAYLOAD_PREFIX + ciphertext

    def unseal(self, node: str, data: bytes) -> bytes:
        if node not in self._nodes:
            raise PermissionError("Unknown Talos node")
        ciphertext = data.removeprefix(_PAYLOAD_PREFIX)
        if ciphertext == data or not _CIPHERTEXT.fullmatch(ciphertext):
            raise ValueError("Invalid sealed Talos payload")
        encoded = self._call("decrypt", "ciphertext", ciphertext.decode(), node)
        try:
            plaintext = base64.b64decode(encoded, validate=True)
        except ValueError:
            raise TransitUnavailable("Invalid Transit plaintext response") from None
        if len(plaintext) != _UNLOCK_BYTES:
            raise TransitUnavailable("Invalid Transit plaintext length")
        return plaintext


def _rpc(
    operation: Callable[[str, bytes], bytes],
    allows_peer: Callable[[str, str], bool] | None = None,
) -> Callable[[bytes, grpc.ServicerContext], bytes]:
    def handle(raw: bytes, context: grpc.ServicerContext) -> bytes:
        try:
            request = REQUEST.FromString(raw)
            if allows_peer is not None and not allows_peer(
                context.peer(), request.node_uuid
            ):
                raise PermissionError("Talos KMS client denied")
            result = operation(request.node_uuid, request.data)
        except PermissionError:
            context.abort(grpc.StatusCode.PERMISSION_DENIED, "Talos KMS client denied")
        except (DecodeError, ValueError):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid Talos KMS request")
        except TransitUnavailable:
            context.abort(grpc.StatusCode.UNAVAILABLE, "OpenBao Transit request failed")
        except Exception:
            context.abort(grpc.StatusCode.INTERNAL, "Talos KMS request failed")
        if not context.is_active():
            context.abort(grpc.StatusCode.CANCELLED, "Talos KMS request cancelled")
        reply = RESPONSE()
        reply.data = result
        return reply.SerializeToString()

    return handle


@contextmanager
def listen_tls(
    adapter: TransitKMS,
    *,
    address: str,
    private_key: bytes,
    certificate: bytes,
    allows_peer: Callable[[str, str], bool] | None = None,
    reload_certificate: Callable[[], tuple[bytes, bytes]] | None = None,
) -> Generator[str]:
    """Serve the Talos protocol on an endpoint with external client admission."""
    with ThreadPoolExecutor(max_workers=_MAX_INFLIGHT) as executor:
        server = grpc.server(
            executor,
            options=(
                ("grpc.max_receive_message_length", MAX_MESSAGE_BYTES),
                ("grpc.max_send_message_length", MAX_MESSAGE_BYTES),
                ("grpc.so_reuseport", 0),
            ),
            maximum_concurrent_rpcs=_MAX_INFLIGHT,
        )
        server.add_generic_rpc_handlers(
            (
                grpc.method_handlers_generic_handler(
                    SERVICE,
                    {
                        "Seal": grpc.unary_unary_rpc_method_handler(
                            _rpc(adapter.seal, allows_peer)
                        ),
                        "Unseal": grpc.unary_unary_rpc_method_handler(
                            _rpc(adapter.unseal, allows_peer)
                        ),
                    },
                ),
            )
        )

        pair = (private_key, certificate)
        configuration = grpc.ssl_server_certificate_configuration([pair])
        certificate_lock = Lock()

        def refresh() -> grpc.ServerCertificateConfiguration:
            nonlocal pair, configuration
            assert reload_certificate is not None
            with certificate_lock:
                try:
                    current = reload_certificate()
                    if current != pair:
                        configuration = grpc.ssl_server_certificate_configuration(
                            [current]
                        )
                        pair = current
                except (OSError, ValueError):
                    pass
                return configuration

        credentials = (
            grpc.ssl_server_credentials([(private_key, certificate)])
            if reload_certificate is None
            else grpc.dynamic_ssl_server_credentials(configuration, refresh)
        )
        port = server.add_secure_port(address, credentials)
        if port == 0:
            raise ValueError("Talos KMS TLS bind failed")
        server.start()
        try:
            yield f"{address.rsplit(':', 1)[0]}:{port}"
        finally:
            server.stop(0).wait()
