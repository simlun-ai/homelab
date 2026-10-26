"""Scoped launcher: isolate imports, disable SDK traffic logs, sanitize failures."""

import logging
import sys
from pathlib import Path

logging.disable(sys.maxsize)
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    try:
        from homelab.yubikey_setup import main

        main()
    except KeyboardInterrupt:
        print(
            "Cancelled. No verification result recorded; reinsert the token before retrying.",
            file=sys.stderr,
        )
        sys.exit(130)
    except Exception:
        # Library exceptions may contain raw USB traffic; never print the exception.
        print(
            "FAILED. No verification result recorded. Check the runbook's failure actions; secret details are suppressed.",
            file=sys.stderr,
        )
        sys.exit(1)
