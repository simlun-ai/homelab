"""Verify public KMS TLS and locked Seal/Unseal behavior from the workstation."""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

import grpc

sys.path.insert(0, str(Path(__file__).resolve().parent))
from homelab.trust_kms import registration, transport  # noqa: E402

HOSTNAME = "kms.k8s-aux.simlun.se"


PROBE = b"Trust KMS public rehearsal probe".ljust(32, b" ")


def probe(channel: grpc.Channel, action: str) -> None:
    rpc: grpc.UnaryUnaryMultiCallable[bytes, bytes] = channel.unary_unary(
        f"/{transport.SERVICE}/{'Seal' if action == 'seal' else 'Unseal'}"
    )
    message = transport.REQUEST()
    if action == "seal":
        message.node_uuid = "11111111-1111-4111-8111-111111111111"
        message.data = PROBE
        try:
            rpc(message.SerializeToString(), timeout=5)
        except grpc.RpcError as exc:
            if exc.code() != grpc.StatusCode.PERMISSION_DENIED:
                raise
        else:
            raise ValueError("Unregistered UUID was admitted")
    else:
        encoded = sys.stdin.buffer.read(8193)
        if len(encoded) > 8192:
            raise ValueError("Oversized probe")
        message.data = base64.b64decode(encoded.strip(), validate=True)
    message.node_uuid = registration.NODE
    result = transport.RESPONSE.FromString(rpc(message.SerializeToString(), timeout=5))
    if action == "seal":
        if not result.data:
            raise ValueError("Empty sealed probe")
        print(base64.b64encode(result.data).decode("ascii"))
    elif result.data != PROBE:
        raise ValueError("Recovered probe did not match")
    else:
        print("PASS: recovered the public probe with the enrolled Trust key.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", nargs="?", choices=("locked", "seal", "unseal"), default="locked"
    )
    args = parser.parse_args()
    try:
        roots = Path("/etc/ssl/certs/ca-certificates.crt").read_bytes()
        with grpc.secure_channel(
            f"{HOSTNAME}:443", grpc.ssl_channel_credentials(roots)
        ) as channel:
            grpc.channel_ready_future(channel).result(timeout=10)
            if args.action != "locked":
                probe(channel, args.action)
                return 0
            for method in ("Seal", "Unseal"):
                rpc: grpc.UnaryUnaryMultiCallable[bytes, bytes] = channel.unary_unary(
                    f"/{transport.SERVICE}/{method}"
                )
                message = transport.REQUEST()
                message.node_uuid = "11111111-1111-4111-8111-111111111111"
                message.data = b"p" * 32
                try:
                    rpc(message.SerializeToString(), timeout=5)
                except grpc.RpcError as exc:
                    if exc.code() != grpc.StatusCode.FAILED_PRECONDITION:
                        raise ValueError() from None
                else:
                    raise ValueError()
        print(
            "PASS: system-trusted TLS and hostname verified; Seal and Unseal report KMS locked."
        )
    except Exception:
        print(
            "KMS TLS/RPC check failed; check DNS, firewall, TLS authorization and service state.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
