"""Isolated launcher; never include SDK or subprocess exception details."""
import logging
from pathlib import Path
import sys

logging.disable(sys.maxsize)
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == '__main__':
    try:
        from homelab.coordinator_password import main
        main()
    except KeyboardInterrupt:
        print('Cancelled; inspect the ciphertext record before retrying.', file=sys.stderr)
        sys.exit(130)
    except Exception:
        print('Failed; secret details suppressed. See the coordinator password runbook. '
              'An interrupted apply may have succeeded; retry the same record.', file=sys.stderr)
        sys.exit(1)
