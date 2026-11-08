"""Software-only session lifecycle and deterministic in-flight race tests."""

import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

from homelab.trust_kms import envelope as e
from homelab.trust_kms import session as s
from kms_vector import VECTOR as V

NODE, ID = V["node"], V["key_id"]
OLD = ID[:-1] + "2"
KEY, PLAIN = bytes.fromhex(V["key_hex"]), bytes.fromhex(V["plaintext_hex"])


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class SessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = Clock()
        self.policy = {NODE: s.Policy(frozenset((ID, OLD)), ID)}
        self.session = s.Session(self.policy, clock=self.clock)

    def open(self, grants: list[s.Grant] | None = None) -> s.Status:
        return self.session.activate(
            self.session.status().instance,
            str(uuid4()),
            [s.Grant(NODE, ID, KEY)] if grants is None else grants,
        )

    def test_starts_locked(self) -> None:
        self.assertEqual(self.session.status().state, "locked")
        with self.assertRaises(s.Locked):
            self.session.seal(NODE, PLAIN)
        with self.assertRaises(s.Locked):
            self.session.unseal(NODE, V["envelope"].encode())

    def test_traffic_does_not_extend_exact_hour(self) -> None:
        opened = self.open()
        self.assertEqual(opened.remaining, 3600)
        self.clock.now += 100
        ciphertext = self.session.seal(NODE, PLAIN)
        self.assertEqual(self.session.unseal(NODE, ciphertext), PLAIN)
        self.assertEqual(self.session.status().remaining, 3500)
        self.clock.now += 3500
        self.session.expire()  # Future daemon must schedule this, even without traffic.
        status = self.session.status()
        self.assertEqual(
            (status.state, status.remaining, status.authorized), ("locked", 0, ())
        )
        with self.assertRaises(s.Locked):
            self.session.unseal(NODE, ciphertext)

    def test_wall_clock_is_not_used_and_suspend_advance_expires(self) -> None:
        self.open()
        with patch.object(
            s.time, "time", side_effect=AssertionError("Wall clock used")
        ):
            self.session.seal(NODE, PLAIN)
            self.clock.now += 3601
            with self.assertRaises(s.Locked):
                self.session.seal(NODE, PLAIN)
        with patch.object(s.time, "clock_gettime", return_value=7.0) as clock:
            self.assertEqual(s.boottime(), 7.0)
            clock.assert_called_once_with(s.time.CLOCK_BOOTTIME)

    def test_active_activation_is_rejected_until_explicit_lock(self) -> None:
        first = self.open()
        self.clock.now += 20
        with self.assertRaises(s.Locked):
            self.open()
        self.assertEqual(self.session.status().session_id, first.session_id)
        self.assertEqual(self.session.status().remaining, 3580)
        self.session.lock()
        second = self.open()
        self.assertNotEqual(first.session_id, second.session_id)
        self.assertEqual(second.remaining, 3600)

    def test_lost_acknowledgment_is_queryable_and_not_replayed_after_lock(self) -> None:
        instance = self.session.status().instance
        request = str(uuid4())
        ack = self.session.activate(instance, request, [s.Grant(NODE, ID, KEY)])
        self.clock.now += 100
        status = (
            self.session.status()
        )  # Simulate client missing activation acknowledgment.
        self.assertEqual(
            (status.request_id, status.session_id), (request, ack.session_id)
        )
        with self.assertRaises(s.Locked):
            self.session.activate(instance, request, [s.Grant(NODE, ID, KEY)])
        self.session.lock()
        self.assertEqual(self.session.status().request_id, request)
        with self.assertRaises(s.Locked):
            self.session.activate(instance, request, [s.Grant(NODE, ID, KEY)])
        self.assertEqual(self.session.status().state, "locked")

    def test_expiry_cannot_replay_activation(self) -> None:
        first = self.open()
        self.clock.now += 3600
        self.session.expire()
        assert first.request_id is not None
        with self.assertRaises(s.Locked):
            self.session.activate(
                first.instance, first.request_id, [s.Grant(NODE, ID, KEY)]
            )
        self.open()

    def test_restart_rotates_instance_and_preserves_no_authority(self) -> None:
        old = self.open()
        ciphertext = self.session.seal(NODE, PLAIN)
        self.session.restart()
        now = self.session.status()
        self.assertNotEqual(old.instance, now.instance)
        self.assertEqual((now.state, now.authorized), ("locked", ()))
        with self.assertRaises(s.Denied):
            self.session.activate(old.instance, str(uuid4()), [s.Grant(NODE, ID, KEY)])
        with self.assertRaises(s.Locked):
            self.session.unseal(NODE, ciphertext)
        self.open()
        self.assertEqual(self.session.unseal(NODE, ciphertext), PLAIN)

    def test_invalid_batch_is_atomic(self) -> None:
        for grants, error in (
            ([], e.InvalidArgument),
            ([s.Grant(NODE, ID, KEY), s.Grant(NODE, ID, KEY)], e.InvalidArgument),
            ([s.Grant(NODE, ID, KEY), s.Grant(NODE, OLD, b"bad")], e.InvalidArgument),
            ([s.Grant(NODE, ID, KEY), s.Grant(str(uuid4()), OLD, KEY)], s.Denied),
            ([s.Grant(NODE, ID, KEY), s.Grant(NODE, ID[:-1] + "9", KEY)], s.Denied),
        ):
            with self.subTest(error=error), self.assertRaises(error):
                self.open(grants)
            self.assertEqual(self.session.status().authorized, ())
        self.open()

    def test_generations_must_be_registered_and_authorized(self) -> None:
        old_payload = e.seal(KEY, NODE, OLD, PLAIN)
        self.open()
        with self.assertRaises(s.Denied):
            self.session.unseal(NODE, old_payload)
        with self.assertRaises(s.Denied):
            self.session.seal(str(uuid4()), PLAIN)
        self.session.lock()
        self.open([s.Grant(NODE, OLD, KEY)])
        self.assertEqual(self.session.unseal(NODE, old_payload), PLAIN)
        with self.assertRaises(s.Denied):
            self.session.seal(
                NODE, PLAIN
            )  # No fallback to OLD when active Seal key absent.
        self.session.lock()
        self.open([s.Grant(NODE, ID, KEY), s.Grant(NODE, OLD, KEY)])
        self.assertEqual(self.session.unseal(NODE, old_payload), PLAIN)
        self.assertEqual(
            e.parse(self.session.seal(NODE, PLAIN), NODE, [ID])["key_id"], ID
        )

    def test_wrapped_node_key_uses_existing_hsm_library(self) -> None:
        from homelab_secrets import wrapping
        from homelab_secrets.cli import FAKE_ROOT, fake_responder

        with fake_responder() as respond:
            record = wrapping.wrap(KEY, ID, FAKE_ROOT, 1, respond)
            recovered = wrapping.unwrap(record, ID, FAKE_ROOT, respond)
        self.open([s.Grant(NODE, ID, recovered)])
        self.assertEqual(
            self.session.unseal(NODE, self.session.seal(NODE, PLAIN)), PLAIN
        )

    def test_registration_and_batch_limits(self) -> None:
        for policies in (
            {},
            {NODE: s.Policy(frozenset(), ID)},
            {NODE: s.Policy(frozenset((ID,)), OLD)},
            {NODE: self.policy[NODE], str(uuid4()): self.policy[NODE]},
        ):
            with self.assertRaises(e.InvalidArgument):
                s.Session(policies, clock=self.clock)
        with patch.object(s, "MAX_GRANTS", 1):
            with self.assertRaises(e.InvalidArgument):
                self.open([s.Grant(NODE, ID, KEY), s.Grant(NODE, OLD, KEY)])
        self.assertEqual(self.session.status().state, "locked")
        self.open()
        unknown = e.seal(KEY, NODE, ID[:-1] + "9", PLAIN)
        with self.assertRaises(s.Denied):
            self.session.unseal(NODE, unknown)

    def test_bad_clock_drops_authority(self) -> None:
        for invalid in (999.0, float("nan"), float("inf")):
            self.clock.now = 1000.0
            self.session = s.Session(self.policy, clock=self.clock)
            self.open()
            self.clock.now = invalid
            with self.assertRaises(s.Locked):
                self.session.status()
            self.clock.now = 1000.0
            self.assertEqual(self.session.status().state, "locked")

    def test_retained_activation_ids_are_bounded(self) -> None:
        with patch.object(s, "MAX_REQUESTS", 1):
            self.open()
            self.session.lock()
            with self.assertRaises(s.Capacity):
                self.open()

    def test_racing_operation_is_discarded_and_capacity_released(self) -> None:
        for transition in ("lock", "expire", "restart", "replace"):
            with self.subTest(transition=transition):
                self.check_race(transition)

    def check_race(self, transition: str) -> None:
        self.clock.now = 1000
        self.session = s.Session(self.policy, clock=self.clock)
        self.open()
        entered, resume = threading.Event(), threading.Event()
        errors: list[Exception] = []
        results: list[bytes] = []
        native_seal = e.seal

        def delayed(key: bytes, node: str, identifier: str, data: bytes) -> bytes:
            entered.set()
            if not resume.wait(5):
                raise TimeoutError("Public test synchronization failed")
            return native_seal(key, node, identifier, data)

        def request() -> None:
            try:
                results.append(self.session.seal(NODE, PLAIN))
            except Exception as exc:
                errors.append(exc)

        with (
            patch.object(e, "seal", side_effect=delayed),
            patch.object(s, "MAX_INFLIGHT", 1),
        ):
            worker = threading.Thread(target=request)
            worker.start()
            try:
                self.assertTrue(entered.wait(5))
                with self.assertRaises(s.Capacity):
                    self.session.seal(NODE, PLAIN)
                if transition == "expire":
                    self.clock.now += 3600
                    self.session.expire()
                elif transition == "restart":
                    self.session.restart()
                else:
                    self.session.lock()
                if transition == "replace":
                    self.open()
            finally:
                resume.set()
                worker.join(5)
            self.assertFalse(worker.is_alive())
        self.assertEqual(results, [])
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], s.Locked)
        if transition != "replace":
            self.open()
        self.session.seal(NODE, PLAIN)

    def test_decrypted_secret_finishing_after_expiry_is_not_released(self) -> None:
        self.open()
        payload = self.session.seal(NODE, PLAIN)
        decrypt = e.unseal

        def late(key: bytes, node: str, identifier: str, data: bytes) -> bytes:
            result = decrypt(key, node, identifier, data)
            self.clock.now += 3600
            return result

        with patch.object(e, "unseal", side_effect=late):
            with self.assertRaises(s.Locked):
                self.session.unseal(NODE, payload)
        self.assertEqual(self.session.status().authorized, ())

    def test_crypto_failure_does_not_consume_capacity_or_extend_window(self) -> None:
        self.open()
        with patch.object(s, "MAX_INFLIGHT", 1):
            with self.assertRaises(e.InvalidArgument):
                self.session.seal(NODE, b"bad")
            self.session.seal(NODE, PLAIN)
        self.assertEqual(self.session.status().remaining, 3600)
        self.assertNotIn(KEY.hex(), repr(s.Grant(NODE, ID, KEY)))


if __name__ == "__main__":
    unittest.main()
