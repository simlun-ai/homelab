"""Trust entry point for the cluster tool installer."""

import sys
from pathlib import Path

SCOPE = Path(__file__).resolve().parent
sys.path.insert(0, str(SCOPE.parents[1]))
from clusters.common import tooling  # noqa: E402


def version(component: str) -> str:
    return tooling.version(component, SCOPE)


if __name__ == "__main__":
    raise SystemExit(tooling.main(SCOPE, ("talosctl", "kubectl", "htpasswd")))
