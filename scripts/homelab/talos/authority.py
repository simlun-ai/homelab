"""Read the existing Talos authority from protected config bytes."""

import base64
from typing import cast

import yaml

from . import bootstrap


def field(value: object, name: str) -> object:
    if not isinstance(value, dict):
        raise ValueError("Expected YAML mapping")
    return cast(dict[str, object], value)[name]


def decode(value: object) -> bytes:
    if not isinstance(value, str):
        raise ValueError("Expected encoded credential field")
    decoded = base64.b64decode(value, validate=True)
    if not 0 < len(decoded) <= bootstrap.MAX_SECRETS:
        raise ValueError("Invalid credential field size")
    return decoded


def load(content: bytes) -> object:
    if not 0 < len(content) <= bootstrap.MAX_SECRETS:
        raise ValueError("Invalid YAML input size")
    return yaml.safe_load(content)


def talos_ca(bundle: bytes) -> tuple[bytes, bytes]:
    """Read the existing OS authority; missing fields must never regenerate it."""
    authority = field(field(load(bundle), "certs"), "os")
    return decode(field(authority, "crt")), decode(field(authority, "key"))
