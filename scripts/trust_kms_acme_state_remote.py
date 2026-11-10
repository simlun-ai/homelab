"""Staging state generation/recovery inside the coordinator's isolated tmpfs."""

import base64
import json
import os
import resource
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import trust_kms_acme_rehearsal as acme  # noqa: E402
from trust_kms_acme_state import LIMIT, WORKSPACE, restore, snapshot  # noqa: E402


def main() -> int:
    created = False
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        os.umask(0o077)
        acme.require_coordinator_hardening()
        fd = os.open(acme.RAM_ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            acme.require_noswap_mount(fd)
        finally:
            os.close(fd)
        request = json.loads(sys.stdin.buffer.read(2 * LIMIT + 1))
        email = request["email"]
        if (
            not isinstance(email, str)
            or len(email) > 254
            or not acme.EMAIL.fullmatch(email)
        ):
            raise ValueError()
        token = base64.b64decode(request["token"], validate=True)
        if not acme.TOKEN.fullmatch(token):
            raise ValueError()
        WORKSPACE.mkdir(mode=0o700)
        created = True
        accounts: dict[Path, bytes] = {}
        recovered = request["state"] is not None
        if recovered:
            restore(WORKSPACE, base64.b64decode(request["state"], validate=True))
            # Inspect before contacting ACME. Expired certificates can still be renewed,
            # but this staging acceptance deliberately requires valid recovered state.
            before, key = acme.inspect_certificate(WORKSPACE)
            accounts = {
                p.relative_to(WORKSPACE): p.read_bytes()
                for p in (WORKSPACE / "config/accounts").rglob("private_key.json")
            }
            if len(accounts) != 1:
                raise ValueError()
        else:
            before, key = b"", b""
        (WORKSPACE / "cloudflare.ini").write_bytes(
            b"dns_cloudflare_api_token = " + token + b"\n"
        )
        environment = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(WORKSPACE),
            "TMPDIR": str(WORKSPACE),
        }
        for name in ("CONFIG", "CACHE", "DATA", "STATE"):
            environment[f"XDG_{name}_HOME"] = str(WORKSPACE)
        print(
            "Renewing recovered staging state."
            if recovered
            else "Issuing fresh staging state.",
            file=sys.stderr,
            flush=True,
        )
        subprocess.run(
            acme.certbot_command(WORKSPACE, email, renew=recovered),
            cwd=WORKSPACE,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=acme.CERTBOT_TIMEOUT,
        )
        after, new_key = acme.inspect_certificate(WORKSPACE)
        after_accounts = {
            p.relative_to(WORKSPACE): p.read_bytes()
            for p in (WORKSPACE / "config/accounts").rglob("private_key.json")
        }
        if recovered and (
            before == after or key != new_key or after_accounts != accounts
        ):
            raise ValueError()
        sys.stdout.buffer.write(snapshot(WORKSPACE))
        sys.stdout.buffer.flush()
    except subprocess.TimeoutExpired:
        print(
            "Certbot staging state operation timed out after 150 seconds.",
            file=sys.stderr,
        )
        return 1
    except subprocess.CalledProcessError as exc:
        print(
            f"Certbot staging state operation exited with status {exc.returncode}.",
            file=sys.stderr,
        )
        return 1
    except Exception:
        print(
            "ACME state operation failed; private details suppressed.", file=sys.stderr
        )
        return 1
    finally:
        # The transient service's private mount is destroyed even on termination.
        if created:
            shutil.rmtree(WORKSPACE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
