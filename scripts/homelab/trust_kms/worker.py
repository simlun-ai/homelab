"""Private process and IPC for one KMS key window."""

from __future__ import annotations

import ctypes
import multiprocessing
import os
import signal
import threading
from collections.abc import Callable, Mapping, Sequence
from multiprocessing.connection import Connection
from typing import cast

from . import envelope, session

IPC_TIMEOUT = 3.0
MAX_REPLY_BYTES = 8192
ERRORS = {
    "FAILED_PRECONDITION": session.Locked,
    "PERMISSION_DENIED": session.Denied,
    "INVALID_ARGUMENT": envelope.InvalidArgument,
    "RESOURCE_EXHAUSTED": session.Capacity,
}


class Unavailable(RuntimeError):
    pass


def _parent_guard(parent: int) -> None:
    libc = ctypes.CDLL(None)
    # Set the parent-death signal before checking for death during spawn.
    prctl = libc.prctl
    prctl.argtypes = [
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    prctl.restype = ctypes.c_int
    if (
        prctl(1, signal.SIGKILL, 0, 0, 0) != 0  # PR_SET_PDEATHSIG
        or os.getppid() != parent
        or prctl(4, 0, 0, 0, 0) != 0  # PR_SET_DUMPABLE
    ):
        raise Unavailable()


def _result[**P, T](
    operation: Callable[P, T], /, *args: P.args, **kwargs: P.kwargs
) -> T | str:
    try:
        return operation(*args, **kwargs)
    except (
        session.Locked,
        session.Denied,
        session.Capacity,
        envelope.InvalidArgument,
    ) as exc:
        return str(exc)


def _send(pipe: Connection, result: bytes | str) -> None:
    # The supervisor never unpickles data from the worker.
    if isinstance(result, bytes):
        pipe.send_bytes(b"\x00" + result)
    else:
        pipe.send_bytes(b"\x01" + result.encode("ascii"))


def _serve(pipe: Connection, parent: int, policies: dict[str, session.Policy]) -> None:
    with pipe:
        try:
            _parent_guard(parent)
            authority = session.Session(policies)
            request, grants = cast(tuple[str, tuple[session.Grant, ...]], pipe.recv())
            try:
                status = _result(
                    authority.activate, authority.status().instance, request, grants
                )
            finally:
                del grants
            if not isinstance(status, session.Status):
                _send(pipe, status)
                return
            _send(pipe, f"{status.session_id} {status.remaining.hex()}".encode("ascii"))
            while True:
                sealing, node, data = cast(tuple[bool, str, bytes], pipe.recv())
                _send(
                    pipe,
                    _result(authority.seal, node, data)
                    if sealing
                    else _result(authority.unseal, node, data),
                )
                del data
        except Exception:
            # The parent treats an unexpected worker exit as revocation.
            return


class Worker:
    """Serialize requests on a private pipe with no network-facing decoder."""

    def __init__(self, policies: Mapping[str, session.Policy]) -> None:
        ctx = multiprocessing.get_context("spawn")
        self._pipe, child = ctx.Pipe()
        self.io = threading.Lock()
        self._closed = False
        self.process = ctx.Process(
            target=_serve, args=(child, os.getpid(), dict(policies)), daemon=True
        )
        try:
            self.process.start()
        except BaseException:
            self._pipe.close()
            raise
        finally:
            child.close()

    def _exchange(self, request: object) -> bytes:
        if self._closed:
            raise Unavailable()
        try:
            self._pipe.send(request)
            if not self._pipe.poll(IPC_TIMEOUT):
                raise Unavailable()
            result = self._pipe.recv_bytes(MAX_REPLY_BYTES)
        except (EOFError, OSError):
            raise Unavailable() from None
        if result.startswith(b"\x00"):
            return result[1:]
        if result.startswith(b"\x01"):
            error = ERRORS.get(result[1:].decode("ascii", errors="replace"))
            if error is not None:
                raise error()
        raise Unavailable()

    def activate(
        self, request: str, grants: Sequence[session.Grant]
    ) -> tuple[str, float]:
        with self.io:
            result = self._exchange((request, tuple(grants)))
        try:
            epoch, encoded_time = result.decode("ascii").split(" ")
            remaining = float.fromhex(encoded_time)
            epoch = envelope.node_uuid(epoch)
        except (ValueError, OverflowError):
            raise Unavailable() from None
        if not 0 < remaining <= session.WINDOW_SECONDS:
            raise Unavailable()
        return epoch, remaining

    def call(self, sealing: bool, node: str, data: bytes) -> bytes:
        if not self.io.acquire(blocking=False):
            raise session.Capacity()
        try:
            return self._exchange((sealing, node, data))
        finally:
            self.io.release()

    def close(self) -> None:
        if self.process.is_alive():
            try:
                self.process.kill()
            except ProcessLookupError:
                pass
        self.process.join(IPC_TIMEOUT)
        if self.process.is_alive():
            raise Unavailable()
        # The killed peer closes its pipe and releases any blocked exchange.
        with self.io:
            self._closed = True
            self._pipe.close()
