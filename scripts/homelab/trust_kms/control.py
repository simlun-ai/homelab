"""Bounded local KMS authorization for explicitly allowed Unix peers."""

from __future__ import annotations

import json
import os
import socket
import stat
import struct
import threading
import time
from collections.abc import Collection, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

from . import daemon, envelope, session, worker

PROTOCOL = 1
FRAME_LIMIT = 16 * 1024
READ_TIMEOUT = 2.0
_HEADER = struct.Struct("!I")
_PEER = struct.Struct("iII")


def _read(peer: socket.socket, count: int, deadline: float) -> bytes:
    data = bytearray()
    while len(data) < count:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError()
        peer.settimeout(remaining)
        chunk = peer.recv(count - len(data))
        if not chunk:
            raise envelope.InvalidArgument()
        data.extend(chunk)
    return bytes(data)


def receive(peer: socket.socket) -> dict[str, object]:
    deadline = time.monotonic() + READ_TIMEOUT
    length = cast(int, _HEADER.unpack(_read(peer, _HEADER.size, deadline))[0])
    if not 0 < length <= FRAME_LIMIT:
        raise envelope.InvalidArgument()
    try:
        message: object = json.loads(
            _read(peer, length, deadline).decode("utf-8"),
            object_pairs_hook=envelope.unique,
        )
    except (ValueError, RecursionError):
        raise envelope.InvalidArgument() from None
    if not isinstance(message, dict):
        raise envelope.InvalidArgument()
    return cast(dict[str, object], message)


def send(peer: socket.socket, message: dict[str, object]) -> None:
    data = json.dumps(message, separators=(",", ":")).encode("utf-8")
    if not 0 < len(data) <= FRAME_LIMIT:
        raise envelope.InvalidArgument()
    peer.settimeout(READ_TIMEOUT)
    peer.sendall(_HEADER.pack(len(data)) + data)


def _grants(value: object) -> list[session.Grant]:
    if not isinstance(value, list):
        raise envelope.InvalidArgument()
    items = cast(list[object], value)
    if not 0 < len(items) <= session.MAX_GRANTS:
        raise envelope.InvalidArgument()
    grants: list[session.Grant] = []
    for raw in items:
        if not isinstance(raw, dict):
            raise envelope.InvalidArgument()
        item = cast(dict[str, object], raw)
        if item.keys() != {"node_uuid", "key_id", "key"}:
            raise envelope.InvalidArgument()
        key = item["key"]
        if not isinstance(key, str):
            raise envelope.InvalidArgument()
        grants.append(
            session.Grant(
                envelope.node_uuid(item["node_uuid"]),
                envelope.key_id(item["key_id"]),
                envelope.decode(key, 32),
            )
        )
    return grants


def _status(status: session.Status) -> dict[str, object]:
    return {
        "protocol": PROTOCOL,
        "instance": status.instance,
        "state": status.state,
        "request_id": status.request_id,
        "session_id": status.session_id,
        "remaining": status.remaining,
        "authorized": status.authorized,
    }


def _dispatch(
    authority: daemon.Authority, request: dict[str, object]
) -> dict[str, object]:
    version = request.get("protocol")
    if type(version) is not int or version != PROTOCOL:
        raise envelope.InvalidArgument()
    action = request.get("action")
    if action == "open-boot-window":
        if request.keys() != {
            "protocol",
            "action",
            "expected_instance",
            "request_id",
            "grants",
        }:
            raise envelope.InvalidArgument()
        return _status(
            authority.activate(
                envelope.node_uuid(request["expected_instance"]),
                envelope.node_uuid(request["request_id"]),
                _grants(request["grants"]),
            )
        )
    if request.keys() != {"protocol", "action"} or action not in ("status", "lock-KMS"):
        raise envelope.InvalidArgument()
    if action == "lock-KMS":
        authority.lock()
    return _status(authority.status())


def _handle(
    peer: socket.socket, authority: daemon.Authority, allowed_uids: Collection[int]
) -> None:
    response: dict[str, object]
    try:
        _, uid, _ = cast(
            tuple[int, int, int],
            _PEER.unpack(
                peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, _PEER.size)
            ),
        )
        if uid not in allowed_uids:
            raise session.Denied()
        response = _dispatch(authority, receive(peer))
    except (
        session.Locked,
        session.Denied,
        session.Capacity,
        envelope.InvalidArgument,
    ) as exc:
        response = {"protocol": PROTOCOL, "error": str(exc)}
    except worker.Unavailable:
        response = {"protocol": PROTOCOL, "error": "UNAVAILABLE"}
    except OSError:
        return
    except Exception:
        response = {"protocol": PROTOCOL, "error": "INTERNAL"}
    try:
        send(peer, response)
    except OSError:
        pass  # A lost acknowledgment must not restart an activated window.


@contextmanager
def listen(
    authority: daemon.Authority,
    path: Path,
    *,
    allowed_uids: Collection[int],
) -> Generator[None]:
    """Use a pre-existing, owner-controlled directory and a fresh socket path."""
    info = path.parent.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o022
    ):
        raise ValueError("KMS control socket requires a protected parent directory")
    uids = frozenset(allowed_uids)
    stop = threading.Event()

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(os.fspath(path))
        try:
            path.chmod(0o660)
            listener.listen(4)
            listener.settimeout(0.25)

            def serve() -> None:
                while not stop.is_set():
                    try:
                        peer, _ = listener.accept()
                    except TimeoutError:
                        continue
                    with peer:
                        _handle(peer, authority, uids)

            server = threading.Thread(target=serve, name="kms-local-control")
            server.start()
            try:
                yield
            finally:
                stop.set()
                server.join()
        finally:
            path.unlink()
