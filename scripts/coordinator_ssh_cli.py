"""Isolated launcher; SDK and subprocess failures never expose secret details."""

import logging
import sys
from pathlib import Path

logging.disable(sys.maxsize)
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    from homelab.record_store import StoreUnavailable

    try:
        from homelab.coordinator_ssh import main

        main()
    except StoreUnavailable as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print(
            "Cancelled. Inspect record/public files and agent state before retrying.",
            file=sys.stderr,
        )
        sys.exit(130)
    except Exception:
        print(
            "Failed; secret details suppressed. See runbooks/coordinator-ssh-key.md. "
            "For check/load, ensure the local agent is running and run ssh-key-load. "
            "An interrupted load may have succeeded; use ssh-key-unload if needed.",
            file=sys.stderr,
        )
        sys.exit(1)
