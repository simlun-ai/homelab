"""In-process session model. A future daemon must schedule expiry and isolate keys."""

import math
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from uuid import uuid4

from . import envelope

WINDOW_SECONDS = 3600
MAX_NODES = 16
MAX_GENERATIONS = 8
MAX_GRANTS = 64
MAX_REQUESTS = 1024
MAX_INFLIGHT = 8


class Locked(RuntimeError):
    def __init__(self) -> None:
        super().__init__("FAILED_PRECONDITION")


class Denied(RuntimeError):
    def __init__(self) -> None:
        super().__init__("PERMISSION_DENIED")


class Capacity(RuntimeError):
    def __init__(self) -> None:
        super().__init__("RESOURCE_EXHAUSTED")


def boottime() -> float:
    # Includes suspend time; never silently substitute wall time or MONOTONIC.
    return time.clock_gettime(time.CLOCK_BOOTTIME)


@dataclass(frozen=True)
class Policy:
    allowed: frozenset[str]
    seal_id: str


@dataclass(frozen=True, repr=False)
class Grant:
    node: str
    key_id: str
    key: bytes = field(repr=False)


@dataclass(frozen=True)
class Status:
    instance: str
    state: str
    request_id: str | None
    session_id: str | None
    remaining: float
    authorized: tuple[tuple[str, str], ...]


@dataclass(repr=False)
class Window:
    session_id: str
    deadline: float
    keys: dict[tuple[str, str], bytes]


class Session:
    """Trusted local caller API; it does not authenticate SSH/socket peers or touch."""

    def __init__(
        self, policies: Mapping[str, Policy], *, clock: Callable[[], float] = boottime
    ) -> None:
        if not 0 < len(policies) <= MAX_NODES:
            raise envelope.InvalidArgument()
        self._policies: dict[str, Policy] = {}
        identifiers: set[str] = set()
        for node, policy in policies.items():
            canonical = envelope.node_uuid(node)
            if (
                canonical in self._policies
                or not 0 < len(policy.allowed) <= MAX_GENERATIONS
                or policy.seal_id not in policy.allowed
            ):
                raise envelope.InvalidArgument()
            allowed = frozenset(envelope.key_id(value) for value in policy.allowed)
            if identifiers & allowed:
                raise envelope.InvalidArgument()
            identifiers.update(allowed)
            self._policies[canonical] = Policy(allowed, policy.seal_id)
        self._clock = clock
        self._mutex = threading.RLock()
        self._window: Window | None = None
        self._seen: set[str] = set()
        self._request_id: str | None = None
        self._session_id: str | None = None
        self._instance = str(uuid4())
        self._last_time = float("-inf")
        self._inflight = 0

    def _clear(self) -> None:
        if self._window is not None:
            self._window.keys.clear()
        self._window = None

    def _now(self) -> float:
        try:
            now = self._clock()
        except Exception:
            self._clear()
            raise Locked() from None
        if not math.isfinite(now) or now < self._last_time:
            self._clear()
            raise Locked()
        self._last_time = now
        if self._window is not None and now >= self._window.deadline:
            self._clear()
        return now

    def expire(self) -> None:
        """Daemon must call this at the deadline even when no requests arrive."""
        with self._mutex:
            self._now()

    def status(self) -> Status:
        with self._mutex:
            now = self._now()
            window = self._window
            return Status(
                self._instance,
                "locked" if window is None else "active",
                self._request_id,
                self._session_id,
                0 if window is None else window.deadline - now,
                () if window is None else tuple(sorted(window.keys)),
            )

    def activate(
        self, expected_instance: str, request_id: str, grants: Sequence[Grant]
    ) -> Status:
        with self._mutex:
            self._now()
            if expected_instance != self._instance:
                raise Denied()
            request_id = envelope.node_uuid(request_id)
            if request_id in self._seen or self._window is not None:
                raise Locked()
            if len(self._seen) >= MAX_REQUESTS:
                raise Capacity()
            if not 0 < len(grants) <= MAX_GRANTS:
                raise envelope.InvalidArgument()
            staged: dict[tuple[str, str], bytes] = {}
            for grant in grants:
                node = envelope.node_uuid(grant.node)
                policy = self._policies.get(node)
                if policy is None or grant.key_id not in policy.allowed:
                    raise Denied()
                pair = (node, grant.key_id)
                if pair in staged:
                    raise envelope.InvalidArgument()
                staged[pair] = envelope.raw_key(grant.key)
            # Start the hour only after the complete batch has passed validation.
            now = self._now()
            self._request_id, self._session_id = request_id, str(uuid4())
            self._seen.add(request_id)
            self._window = Window(self._session_id, now + WINDOW_SECONDS, staged)
            return self.status()

    def lock(self) -> None:
        with self._mutex:
            self._clear()

    def release(self, epoch: str | None, data: bytes) -> bytes:
        with self._mutex:
            self._now()
            if self._window is None or self._window.session_id != epoch:
                raise Locked()
            return data

    def restart(self) -> None:
        """Model restart: drop authority and old activation IDs; rotate instance ID."""
        with self._mutex:
            self._clear()
            self._instance = str(uuid4())
            self._seen.clear()
            self._request_id = self._session_id = None
            # Keep the in-flight count until old operations actually exit.

    def _perform(self, node: str, data: bytes, *, sealing: bool) -> bytes:
        with self._mutex:
            self._now()
            window = self._window
            if window is None:
                raise Locked()
            node = envelope.node_uuid(node)
            policy = self._policies.get(node)
            if policy is None:
                raise Denied()
            try:
                identifier = (
                    policy.seal_id
                    if sealing
                    else envelope.parse(data, node, policy.allowed)["key_id"]
                )
            except envelope.UnknownGeneration:
                raise Denied() from None
            key = window.keys.get((node, identifier))
            if key is None:
                raise Denied()
            if self._inflight >= MAX_INFLIGHT:
                raise Capacity()
            self._inflight += 1
            epoch = window.session_id
        try:
            result = (
                envelope.seal(key, node, identifier, data)
                if sealing
                else envelope.unseal(key, node, identifier, data)
            )
            return self.release(epoch, result)
        finally:
            with self._mutex:
                self._inflight -= 1

    def seal(self, node: str, plaintext: bytes) -> bytes:
        return self._perform(node, plaintext, sealing=True)

    def unseal(self, node: str, encoded: bytes) -> bytes:
        return self._perform(node, encoded, sealing=False)
