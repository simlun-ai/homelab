"""Supervise the one-hour key worker and gate KMS responses by session epoch."""

from __future__ import annotations

import math
import threading
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import contextmanager
from uuid import uuid4

from . import envelope, session, worker

EXPIRY_POLL_SECONDS = 0.25


class Authority:
    def __init__(
        self,
        policies: Mapping[str, session.Policy],
        *,
        clock: Callable[[], float] = session.boottime,
    ) -> None:
        self._policies = dict(policies)
        session.Session(self._policies)  # Validate the public configuration at startup.
        self._clock = clock
        self._last_time = float("-inf")
        self._mutex = threading.RLock()
        self._stop = threading.Event()
        self._instance = str(uuid4())
        self._request_id: str | None = None
        self._session_id: str | None = None
        self._seen: set[str] = set()
        self._deadline: float | None = None
        self._authorized: tuple[tuple[str, str], ...] = ()
        self.worker: worker.Worker | None = None

    def _revoke(self) -> None:
        self._deadline = None
        self._authorized = ()
        if self.worker is not None:
            self.worker.close()
            self.worker = None

    def _refresh(self) -> float:
        try:
            now = self._clock()
        except Exception:
            self._revoke()
            raise session.Locked() from None
        if not math.isfinite(now) or now < self._last_time:
            self._revoke()
            raise session.Locked()
        self._last_time = now
        if self.worker is not None and (
            self._deadline is None
            or now >= self._deadline
            or not self.worker.process.is_alive()
        ):
            self._revoke()
        return now

    def status(self) -> session.Status:
        with self._mutex:
            now = self._refresh()
            deadline = self._deadline
            return session.Status(
                self._instance,
                "locked" if deadline is None else "active",
                self._request_id,
                self._session_id,
                0 if deadline is None else deadline - now,
                self._authorized,
            )

    def activate(
        self, expected_instance: str, request_id: str, grants: Sequence[session.Grant]
    ) -> session.Status:
        with self._mutex:
            self._refresh()
            if expected_instance != self._instance:
                raise session.Denied()
            request_id = envelope.node_uuid(request_id)
            if (
                self._stop.is_set()
                or request_id in self._seen
                or self.worker is not None
            ):
                raise session.Locked()
            if len(self._seen) >= session.MAX_REQUESTS:
                raise session.Capacity()
            if not 0 < len(grants) <= session.MAX_GRANTS:
                raise envelope.InvalidArgument()
            batch = tuple(grants)
            self.worker = worker.Worker(self._policies)
            try:
                epoch, remaining = self.worker.activate(request_id, batch)
                now = self._clock()
                if not math.isfinite(now) or now < self._last_time:
                    raise session.Locked()
                self._last_time = now
                self._deadline = now + remaining
                self._authorized = tuple(
                    sorted(
                        (envelope.node_uuid(grant.node), grant.key_id)
                        for grant in batch
                    )
                )
                self._request_id = request_id
                self._session_id = epoch
                self._seen.add(request_id)
                return self.status()
            except BaseException:
                self._revoke()
                raise

    def lock(self) -> None:
        with self._mutex:
            self._revoke()

    def release(self, epoch: str | None, data: bytes) -> bytes:
        """Authorize handoff to gRPC's serializer for the same live epoch."""
        with self._mutex:
            self._refresh()
            if self._deadline is None or self._session_id != epoch:
                raise session.Locked()
            return data

    def _call(self, sealing: bool, node: str, data: bytes) -> bytes:
        with self._mutex:
            self._refresh()
            current = self.worker
            epoch = self._session_id
            if self._deadline is None or current is None:
                raise session.Locked()
        try:
            result = current.call(sealing, node, data)
        except worker.Unavailable:
            with self._mutex:
                self._refresh()
                if self.worker is not current:
                    raise session.Locked() from None
                self._revoke()
            raise
        return self.release(epoch, result)

    def seal(self, node: str, data: bytes) -> bytes:
        return self._call(True, node, data)

    def unseal(self, node: str, data: bytes) -> bytes:
        return self._call(False, node, data)

    def _expire(self) -> None:
        while not self._stop.wait(EXPIRY_POLL_SECONDS):
            try:
                with self._mutex:
                    self._refresh()
            except (session.Locked, worker.Unavailable):
                # No authority remains. Retry reaping a worker that could not exit.
                continue

    @contextmanager
    def run(self) -> Generator[None]:
        scheduler = threading.Thread(target=self._expire, name="kms-expiry")
        scheduler.start()
        try:
            yield
        finally:
            self._stop.set()
            scheduler.join()
            self.lock()
