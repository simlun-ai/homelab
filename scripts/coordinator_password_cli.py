"""Isolated launcher; never include SDK or subprocess exception details."""

import logging
import sys
from pathlib import Path

logging.disable(sys.maxsize)
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    from homelab.record_store import StoreUnavailable

    try:
        from homelab.coordinator_password import main

        main()
    except StoreUnavailable as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print(
            "Cancelled; inspect the ciphertext record before retrying.", file=sys.stderr
        )
        sys.exit(130)
    except Exception:
        print(
            "Failed; secret details suppressed. See the coordinator password runbook. "
            "An interrupted apply may have succeeded; retry the same record.",
            file=sys.stderr,
        )
        sys.exit(1)
