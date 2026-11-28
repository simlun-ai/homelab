"""Issue a short-lived Headlamp viewer token using the Trust Talos identity."""

import argparse
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trust_tofu as tofu  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ram-root", type=Path, default=Path("/dev/shm"))
    args = parser.parse_args()
    secrets = tofu.recovery.secrets

    try:
        secrets.require_pipe()
        secrets.harden()
        kubectl = secrets.executable(tofu.SCOPE / "bin/kubectl", "kubectl")
        with redirect_stdout(sys.stderr):
            kubeconfig = tofu.get_kubeconfig(args.ram_root)
        with tofu.recovery.config.memory_file(kubeconfig) as fd:
            token = secrets.capture_bundle(
                [
                    kubectl,
                    "--kubeconfig",
                    f"/proc/self/fd/{fd}",
                    "-n",
                    "headlamp",
                    "create",
                    "token",
                    "headlamp-viewer",
                    "--duration=1h",
                ],
                timeout=30,
                pass_fds=(fd,),
            )
        sys.stdout.buffer.write(token)
        sys.stdout.buffer.flush()
    except (OSError, RuntimeError, ValueError, KeyboardInterrupt):
        print(
            "Headlamp login token issuance stopped. Use a pipe to your clipboard.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
