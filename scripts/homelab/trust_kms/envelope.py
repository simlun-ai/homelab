"""Bounded homelab-kms-v1 codec; no record storage, logging or token operations."""

import base64
import json
import os
import re
from collections.abc import Collection
from typing import cast
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

FORMAT = "homelab-kms-v1"
MAX_ENVELOPE = 4096
FIELDS = {"format", "node_uuid", "key_id", "salt", "nonce", "ciphertext", "encoding"}
KEY_ID = re.compile(r"homelab/v1/trust/kms/[a-z0-9-]+/r[1-9][0-9]*", re.ASCII)


class InvalidArgument(ValueError):
    def __init__(self) -> None:
        super().__init__("INVALID_ARGUMENT")


class UnknownGeneration(InvalidArgument):
    pass


def node_uuid(value: object) -> str:
    if not isinstance(value, str):
        raise InvalidArgument()
    try:
        parsed = UUID(value)
        canonical = str(parsed)
        if not parsed.int or value.lower() != canonical:
            raise InvalidArgument()
        return canonical
    except (ValueError, AttributeError, TypeError):
        raise InvalidArgument() from None


def key_id(value: object) -> str:
    if (
        not isinstance(value, str)
        or not 0 < len(value) <= 256
        or not KEY_ID.fullmatch(value)
    ):
        raise InvalidArgument()
    return value


def raw_key(value: object) -> bytes:
    if not isinstance(value, bytes) or len(value) != 32:
        raise InvalidArgument()
    return value


def b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def decode(value: str, size: int) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True)
        if len(raw) != size or b64(raw) != value:
            raise InvalidArgument()
        return raw
    except (ValueError, UnicodeError):
        raise InvalidArgument() from None


def canonical(header: dict[str, str]) -> bytes:
    return json.dumps(
        header, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def derive(key: bytes, salt: bytes, node: str, identifier: str) -> bytes:
    info = b"\0".join(part.encode("ascii") for part in (FORMAT, node, identifier))
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=info).derive(
        raw_key(key)
    )


def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, value in pairs:
        if name in result:
            raise InvalidArgument()
        result[name] = value
    return result


def parse(encoded: bytes, node: str, allowed: Collection[str]) -> dict[str, str]:
    if not 0 < len(encoded) <= MAX_ENVELOPE:
        raise InvalidArgument()
    try:
        value: object = json.loads(encoded.decode("ascii"), object_pairs_hook=unique)
        if not isinstance(value, dict):
            raise InvalidArgument()
        fields = cast(dict[str, object], value)
        if set(fields) != FIELDS or not all(
            isinstance(v, str) for v in fields.values()
        ):
            raise InvalidArgument()
        header = cast(dict[str, str], fields)
        if header["format"] != FORMAT or header["encoding"] != "raw-32":
            raise InvalidArgument()
        if header["node_uuid"] != node_uuid(node) or header["node_uuid"] != node_uuid(
            header["node_uuid"]
        ):
            raise InvalidArgument()
        key_id(header["key_id"])
        decode(header["salt"], 32)
        decode(header["nonce"], 12)
        decode(header["ciphertext"], 48)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise InvalidArgument() from None
    if header["key_id"] not in allowed:
        raise UnknownGeneration()
    return header


def seal(key: bytes, node: str, identifier: str, plaintext: bytes) -> bytes:
    node, identifier = node_uuid(node), key_id(identifier)
    raw_key(plaintext)
    salt, nonce = os.urandom(32), os.urandom(12)
    header = {
        "format": FORMAT,
        "node_uuid": node,
        "key_id": identifier,
        "salt": b64(salt),
        "nonce": b64(nonce),
        "encoding": "raw-32",
    }
    ciphertext = AESGCM(derive(key, salt, node, identifier)).encrypt(
        nonce, plaintext, canonical(header)
    )
    return canonical({**header, "ciphertext": b64(ciphertext)})


def unseal(key: bytes, node: str, identifier: str, encoded: bytes) -> bytes:
    header = parse(encoded, node, (key_id(identifier),))
    ciphertext = decode(header.pop("ciphertext"), 48)
    payload_key = derive(
        key, decode(header["salt"], 32), header["node_uuid"], identifier
    )
    try:
        plaintext = AESGCM(payload_key).decrypt(
            decode(header["nonce"], 12), ciphertext, canonical(header)
        )
    except InvalidTag:
        raise InvalidArgument() from None
    return raw_key(plaintext)
