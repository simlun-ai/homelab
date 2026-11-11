"""Verify public KMS TLS and locked Seal/Unseal behavior from the workstation."""

from __future__ import annotations

import sys
from pathlib import Path

import grpc

sys.path.insert(0, str(Path(__file__).resolve().parent))
from homelab.trust_kms import transport  # noqa: E402

HOSTNAME = "kms.k8s-aux.simlun.se"


def main() -> int:
    try:
        roots = Path("/etc/ssl/certs/ca-certificates.crt").read_bytes()
        with grpc.secure_channel(
            f"{HOSTNAME}:443", grpc.ssl_channel_credentials(roots)
        ) as channel:
            grpc.channel_ready_future(channel).result(timeout=10)
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
            "KMS TLS/locked-RPC check failed; check DNS, firewall, TLS authorization and service state.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
