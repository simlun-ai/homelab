"""Install the bcrypt verifier for the wrapped Trust Zot publisher credential."""

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trust_tofu as tofu  # noqa: E402

KEY_ID = "homelab/v1/trust/zot/publisher/r1"
RECORD = tofu.ROOT / "secrets/wrapped/trust-zot-publisher-r1.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ram-root", type=Path, default=Path("/dev/shm"))
    args = parser.parse_args()
    secrets = tofu.recovery.secrets
    try:
        secrets.harden()
        os.umask(0o077)
        htpasswd = shutil.which("htpasswd")
        if htpasswd is None:
            raise ValueError("Install htpasswd (apache2-utils) on the workstation")
        secrets.require_private_repository(record=RECORD)
        kubectl = secrets.executable(tofu.SCOPE / "bin/kubectl", "kubectl")
        unwrap = secrets.executable(
            Path(sys.executable).with_name("homelab-unwrap"), "homelab-unwrap"
        )
        config = tofu.get_kubeconfig(args.ram_root)
        print("Touch the YubiKey to recover the Zot publisher credential.", flush=True)
        with secrets.hsm_progress_terminal() as terminal:
            password = secrets.recover_bundle(
                unwrap, record=RECORD, key_id=KEY_ID, stderr=terminal
            )
        if not re.fullmatch(rb"[A-Za-z0-9+/]{43}=", password):
            raise ValueError("Expected the enrolled base64 publisher password")
        verifier = subprocess.run(
            [htpasswd, "-niB", "-C", "12", "publisher"],
            input=password + b"\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=15,
        ).stdout
        if not re.fullmatch(rb"publisher:\$2[aby]\$12\$[./A-Za-z0-9]{53}\n", verifier):
            raise ValueError("htpasswd did not produce the expected bcrypt verifier")
        document = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"namespace": "zot", "name": "zot-publisher"},
            "data": {"htpasswd": base64.b64encode(verifier).decode("ascii")},
        }
        with tofu.recovery.config.memory_file(config) as fd:
            subprocess.run(
                [
                    kubectl,
                    "--kubeconfig",
                    f"/proc/self/fd/{fd}",
                    "apply",
                    "--server-side",
                    "-f",
                    "-",
                ],
                input=json.dumps(document).encode(),
                pass_fds=(fd,),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=30,
            )
    except (
        OSError,
        ValueError,
        RuntimeError,
        subprocess.SubprocessError,
        KeyboardInterrupt,
    ):
        print(
            "Zot publisher setup stopped. Check htpasswd, the wrapped record, and namespace zot.",
            file=sys.stderr,
        )
        return 1
    print("Configured zot/zot-publisher.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
