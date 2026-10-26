"""Check the UPS scope's Python support and exact installed requirements."""

import importlib.metadata
import sys
from pathlib import Path

SCOPE = Path(__file__).resolve().parent


def main():
    if not (3, 13) <= sys.version_info[:2] < (3, 15):
        raise SystemExit("UPS tools require Python 3.13–3.14 (Ubuntu 26.04 uses 3.14).")
    if sys.argv[1:] == ["--python-only"]:
        return
    if sys.argv[1:]:
        raise SystemExit("Usage: check-tools.py [--python-only]")
    if Path(sys.prefix).resolve() != (SCOPE / ".venv").resolve():
        raise SystemExit("Use support/ups/.venv/bin/python; run make tools first.")
    for line in (SCOPE / "requirements.txt").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        package, expected = line.split("==")
        try:
            actual = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            actual = "not installed"
        if actual != expected:
            raise SystemExit(
                f"{package}: expected {expected}, got {actual}; run make tools."
            )


if __name__ == "__main__":
    main()
