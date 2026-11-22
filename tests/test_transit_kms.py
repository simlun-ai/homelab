"""Exercise Talos wire requests and the bounded Transit client."""

import base64
import json
import unittest
from unittest.mock import Mock, patch

try:
    import grpc

    from homelab import transit_kms
    from homelab.talos_kms_wire import REQUEST, RESPONSE
except ModuleNotFoundError as error:
    if error.name not in {"grpc", "google", "google.protobuf"}:
        raise
    raise unittest.SkipTest("Install the optional KMS test dependencies") from None

NODE = "00000000-0000-0000-0000-000000000001"
OTHER_NODE = "00000000-0000-0000-0000-000000000002"
UNLOCK = bytes(range(32))
CIPHERTEXT = "vault:v1:c2VhbGVk"


class TransitKMSTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = transit_kms.TransitKMS(
            "https://openbao.example", "talos-backup", [NODE], lambda: "fixture-token"
        )

    @patch("homelab.transit_kms.HTTPSConnection")
    def test_round_trip_binds_ciphertext_to_node(self, connection: Mock) -> None:
        response = connection.return_value.getresponse.return_value
        response.status = 200
        response.read.side_effect = [
            json.dumps({"data": {"ciphertext": CIPHERTEXT}}).encode(),
            json.dumps(
                {"data": {"plaintext": base64.b64encode(UNLOCK).decode()}}
            ).encode(),
        ]
        sealed = self.adapter.seal(NODE, UNLOCK)
        self.assertEqual(sealed, b"homelab-talos-kms-v1:" + CIPHERTEXT.encode())
        self.assertEqual(self.adapter.unseal(NODE, sealed), UNLOCK)
        encrypt, decrypt = connection.return_value.request.call_args_list
        self.assertEqual(encrypt.args[1], "/v1/transit/encrypt/talos-backup")
        self.assertEqual(decrypt.args[1], "/v1/transit/decrypt/talos-backup")
        for call in (encrypt, decrypt):
            data = json.loads(call.args[2])
            self.assertEqual(
                base64.b64decode(data["associated_data"]),
                f"homelab-talos-kms-v1:{NODE}".encode(),
            )

    @patch("homelab.transit_kms.HTTPSConnection")
    def test_malformed_input_and_unknown_node_do_not_call_backend(
        self, connection: Mock
    ) -> None:
        with self.assertRaises(PermissionError):
            self.adapter.seal(OTHER_NODE, UNLOCK)
        with self.assertRaises(ValueError):
            self.adapter.seal(NODE, b"short")
        with self.assertRaises(ValueError):
            self.adapter.unseal(NODE, CIPHERTEXT.encode())
        connection.assert_not_called()

    @patch("homelab.transit_kms.HTTPSConnection")
    def test_backend_error_and_wrong_unlock_length_fail_closed(
        self, connection: Mock
    ) -> None:
        response = connection.return_value.getresponse.return_value
        response.status = 503
        with self.assertRaises(transit_kms.TransitUnavailable):
            self.adapter.seal(NODE, UNLOCK)
        response.read.assert_not_called()
        response.status = 200
        response.read.return_value = b'{"data":{"plaintext":"AA=="}}'
        with self.assertRaises(transit_kms.TransitUnavailable):
            self.adapter.unseal(NODE, b"homelab-talos-kms-v1:" + CIPHERTEXT.encode())

    def test_wire_response_and_backend_failure_status(self) -> None:
        request = REQUEST()
        request.node_uuid = NODE
        request.data = UNLOCK
        wire = request.SerializeToString()
        context = Mock(spec=grpc.ServicerContext)
        handle = transit_kms._rpc(Mock(return_value=UNLOCK))  # pyright: ignore[reportPrivateUsage]
        self.assertEqual(RESPONSE.FromString(handle(wire, context)).data, UNLOCK)
        context.abort.side_effect = grpc.RpcError()
        backend = Mock(side_effect=transit_kms.TransitUnavailable())
        handle = transit_kms._rpc(backend)  # pyright: ignore[reportPrivateUsage]
        with self.assertRaises(grpc.RpcError):
            handle(wire, context)
        context.abort.assert_called_once_with(
            grpc.StatusCode.UNAVAILABLE, "OpenBao Transit request failed"
        )
