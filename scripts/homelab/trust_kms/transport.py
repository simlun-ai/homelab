"""Bounded Talos KMS RPC adapter for the disposable loopback TLS rehearsal."""

from collections.abc import Callable, Generator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol, cast

import grpc
from google.protobuf import descriptor_pb2, message_factory
from google.protobuf.message import DecodeError, Message

from . import envelope, session, worker

SERVICE = "sidero.kms.KMSService"
MAX_MESSAGE_BYTES = 8192


class _Request(Message):
    node_uuid: str
    data: bytes


class _Response(Message):
    data: bytes


def _messages() -> tuple[type[_Request], type[_Response]]:
    # Wire fields from siderolabs/kms-client v0.2.0, api/kms/kms.proto.
    schema = descriptor_pb2.FileDescriptorProto(
        name="kms.proto", package="sidero.kms", syntax="proto3"
    )
    request = schema.message_type.add(name="Request")
    request.field.add(
        name="node_uuid", number=1, type=descriptor_pb2.FieldDescriptorProto.TYPE_STRING
    )
    request.field.add(
        name="data", number=2, type=descriptor_pb2.FieldDescriptorProto.TYPE_BYTES
    )
    response = schema.message_type.add(name="Response")
    response.field.add(
        name="data", number=1, type=descriptor_pb2.FieldDescriptorProto.TYPE_BYTES
    )
    # GetMessages is also available on the coordinator's older APT protobuf.
    classes = message_factory.GetMessages([schema])
    return (
        cast(type[_Request], classes["sidero.kms.Request"]),
        cast(type[_Response], classes["sidero.kms.Response"]),
    )


REQUEST, RESPONSE = _messages()


class _Authority(Protocol):
    def status(self) -> session.Status: ...
    def seal(self, node: str, data: bytes, /) -> bytes: ...
    def unseal(self, node: str, data: bytes, /) -> bytes: ...
    def lock(self) -> None: ...
    def release(self, epoch: str | None, data: bytes) -> bytes: ...


@dataclass(frozen=True, repr=False)
class _Reply:
    epoch: str | None
    data: bytes


def _handler(
    authority: _Authority, operation: Callable[[str, bytes], bytes]
) -> Callable[[bytes, grpc.ServicerContext], _Reply]:
    def handle(raw: bytes, context: grpc.ServicerContext) -> _Reply:
        try:
            before = authority.status()
            if before.state != "active":
                raise session.Locked()
            message = REQUEST.FromString(raw)
            result = operation(message.node_uuid, message.data)
            response = RESPONSE()
            response.data = result
            encoded = response.SerializeToString()
            after = authority.status()
            if after.state != "active" or before.session_id != after.session_id:
                raise session.Locked()
        except session.Locked:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, "KMS locked")
        except session.Denied:
            context.abort(grpc.StatusCode.PERMISSION_DENIED, "KMS request denied")
        except session.Capacity:
            context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, "KMS capacity exhausted")
        except worker.Unavailable:
            context.abort(grpc.StatusCode.UNAVAILABLE, "KMS worker unavailable")
        except (DecodeError, envelope.InvalidArgument):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid KMS request")
        except Exception:
            context.abort(grpc.StatusCode.INTERNAL, "KMS request failed")

        if not context.is_active():
            context.abort(grpc.StatusCode.CANCELLED, "KMS request cancelled")
        return _Reply(before.session_id, encoded)

    return handle


@contextmanager
def listen_tls(
    authority: _Authority, *, private_key: bytes, certificate: bytes, address: str
) -> Generator[str]:
    """Bind only the caller-selected address, using in-memory TLS material."""
    with ThreadPoolExecutor(max_workers=session.MAX_INFLIGHT) as executor:
        server = grpc.server(
            executor,
            options=(
                ("grpc.max_receive_message_length", MAX_MESSAGE_BYTES),
                ("grpc.max_send_message_length", MAX_MESSAGE_BYTES),
                ("grpc.so_reuseport", 0),
            ),
            maximum_concurrent_rpcs=session.MAX_INFLIGHT,
        )

        def serialize(reply: _Reply) -> bytes:
            return authority.release(reply.epoch, reply.data)

        server.add_generic_rpc_handlers(
            (
                grpc.method_handlers_generic_handler(
                    SERVICE,
                    {
                        "Seal": grpc.unary_unary_rpc_method_handler(
                            _handler(authority, authority.seal),
                            response_serializer=serialize,
                        ),
                        "Unseal": grpc.unary_unary_rpc_method_handler(
                            _handler(authority, authority.unseal),
                            response_serializer=serialize,
                        ),
                    },
                ),
            )
        )
        try:
            credentials = grpc.ssl_server_credentials([(private_key, certificate)])
            port = server.add_secure_port(address, credentials)
            if port == 0:
                raise ValueError("TLS bind failed")
            server.start()
            yield address.rsplit(":", 1)[0] + f":{port}"
        finally:
            try:
                authority.lock()
            finally:
                server.stop(0).wait()


@contextmanager
def listen_loopback(
    authority: _Authority, *, private_key: bytes, certificate: bytes
) -> Generator[str]:
    with listen_tls(
        authority,
        private_key=private_key,
        certificate=certificate,
        address="127.0.0.1:0",
    ) as endpoint:
        yield endpoint
