"""Root SSH entry point for bounded TLS delivery and public daemon status."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from homelab.trust_kms import tls  # noqa: E402


def main() -> int:
    try:
        tls.harden_process()
        tls.require_memory_policy()
        if len(sys.argv) != 2 or sys.argv[1] not in ("status", "authorize"):
            raise ValueError()
        if sys.argv[1] == "status":
            status = tls.local("status")
        else:
            message = json.loads(sys.stdin.buffer.read(tls.FRAME_LIMIT + 1))
            if set(message) != {"expected_instance", "private_key", "certificate"}:
                raise ValueError()
            status = tls.local("authorize-tls", **message)
        if status.get("error") is not None:
            raise ValueError()
        # Only daemon-owned public fields may reach the terminal or SSH stdout.
        fields = (
            "protocol",
            "instance",
            "kms_state",
            "tls_state",
            "endpoint",
            "fingerprint",
            "cert_not_after",
        )
        print(json.dumps({field: status[field] for field in fields}))
    except Exception:
        print(
            "TLS control failed. Check service status; an interrupted authorization may have succeeded.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
