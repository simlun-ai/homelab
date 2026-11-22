"""Protobuf wire definitions shared by both Talos KMS services."""

from typing import cast

from google.protobuf import descriptor_pb2, message_factory
from google.protobuf.message import Message

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
