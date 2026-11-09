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
            pipe.send(status)
            if not isinstance(status, session.Status):
                return
            while True:
                sealing, node, data = cast(tuple[bool, str, bytes], pipe.recv())
                pipe.send(
                    _result(authority.seal, node, data)
                    if sealing
                    else _result(authority.unseal, node, data)
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

    def _exchange(self, request: object) -> object:
        if self._closed:
            raise Unavailable()
        try:
            self._pipe.send(request)
            if not self._pipe.poll(IPC_TIMEOUT):
                raise Unavailable()
            result: object = self._pipe.recv()
        except (EOFError, OSError):
            raise Unavailable() from None
        if isinstance(result, str) and result in ERRORS:
            raise ERRORS[result]()
        return result

    def activate(self, request: str, grants: Sequence[session.Grant]) -> session.Status:
        with self.io:
            result = self._exchange((request, tuple(grants)))
        if not isinstance(result, session.Status):
            raise Unavailable()
        return result

    def call(self, sealing: bool, node: str, data: bytes) -> bytes:
        if not self.io.acquire(blocking=False):
            raise session.Capacity()
        try:
            result = self._exchange((sealing, node, data))
        finally:
            self.io.release()
        if not isinstance(result, bytes):
            raise Unavailable()
        return result

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
