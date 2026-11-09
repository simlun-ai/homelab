"""Bounded Talos KMS RPC adapter for the disposable loopback TLS rehearsal."""

from collections.abc import Callable, Generator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import cast

import grpc
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
from google.protobuf.message import DecodeError, Message

from . import envelope, session

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
    pool = descriptor_pool.DescriptorPool()
    pool.Add(schema)
    return (
        cast(
            type[_Request],
            message_factory.GetMessageClass(
                pool.FindMessageTypeByName("sidero.kms.Request")
            ),
        ),
        cast(
            type[_Response],
            message_factory.GetMessageClass(
                pool.FindMessageTypeByName("sidero.kms.Response")
            ),
        ),
    )


REQUEST, RESPONSE = _messages()


def _handler(
    authority: session.Session, operation: Callable[[str, bytes], bytes]
) -> Callable[[bytes, grpc.ServicerContext], bytes]:
    def handle(raw: bytes, context: grpc.ServicerContext) -> bytes:
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
        except (DecodeError, envelope.InvalidArgument):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid KMS request")
        except Exception:
            context.abort(grpc.StatusCode.INTERNAL, "KMS request failed")

        if not context.is_active():
            context.abort(grpc.StatusCode.CANCELLED, "KMS request cancelled")
        return encoded

    return handle


@contextmanager
def listen_loopback(
    authority: session.Session, *, private_key: bytes, certificate: bytes
) -> Generator[str]:
    """Serve only on localhost using caller-supplied PEM TLS material."""
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
        server.add_generic_rpc_handlers(
            (
                grpc.method_handlers_generic_handler(
                    SERVICE,
                    {
                        "Seal": grpc.unary_unary_rpc_method_handler(
                            _handler(authority, authority.seal)
                        ),
                        "Unseal": grpc.unary_unary_rpc_method_handler(
                            _handler(authority, authority.unseal)
                        ),
                    },
                ),
            )
        )
        credentials = grpc.ssl_server_credentials([(private_key, certificate)])
        port = server.add_secure_port("127.0.0.1:0", credentials)
        server.start()
        try:
            yield f"127.0.0.1:{port}"
        finally:
            authority.lock()
            server.stop(0).wait()
