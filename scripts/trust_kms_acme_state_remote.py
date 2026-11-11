"""ACME state generation/recovery inside the coordinator's isolated tmpfs."""

import base64
import configparser
import json
import os
import resource
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import trust_kms_acme_rehearsal as acme  # noqa: E402
from trust_kms_acme_profile import profile  # noqa: E402
from trust_kms_acme_state import LIMIT, WORKSPACE, restore, snapshot  # noqa: E402

CA_FILE = Path("/etc/ssl/certs/ca-certificates.crt")


def verify_production(
    workspace: Path, *, allow_expired: bool = False, ca_file: Path = CA_FILE
) -> None:
    lineage = workspace / "config/live" / acme.HOSTNAME
    if (lineage / "fullchain.pem").read_bytes() != (
        lineage / "cert.pem"
    ).read_bytes() + (lineage / "chain.pem").read_bytes():
        raise ValueError("Full chain does not match the certificate and chain")
    try:
        subprocess.run(
            [
                "/usr/bin/openssl",
                "verify",
                "-CAfile",
                str(ca_file),
                "-no-CApath",
                "-no-CAstore",
                "-purpose",
                "sslserver",
                "-verify_hostname",
                acme.HOSTNAME,
                *(["-no_check_time"] if allow_expired else []),
                "-untrusted",
                str(lineage / "chain.pem"),
                str(lineage / "cert.pem"),
            ],
            env={"PATH": "/usr/bin:/bin", "OPENSSL_CONF": "/dev/null"},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        raise acme.RehearsalError(
            "Production certificate chain verification failed against system trust."
        ) from None


def command(workspace: Path, email: str, *, renew: bool, environment: str) -> list[str]:
    argv = acme.certbot_command(workspace, email, renew=renew)
    argv[argv.index("--server") + 1] = profile(environment).server
    if environment == "production" and "--force-renewal" in argv:
        argv.remove("--force-renewal")
    return argv


def check_renewal_config(workspace: Path, environment: str) -> None:
    config = configparser.ConfigParser(interpolation=None)
    # Certbot uses ConfigObj: lineage metadata precedes [renewalparams].
    # Give those top-level keys a synthetic section for the stdlib INI parser.
    filename = workspace / "config/renewal" / f"{acme.HOSTNAME}.conf"
    config.read_string("[lineage]\n" + filename.read_text(encoding="utf-8"))
    parameters = config["renewalparams"]
    if (
        parameters["server"] != profile(environment).server
        or parameters["authenticator"] != "dns-cloudflare"
        or parameters["dns_cloudflare_credentials"] != str(workspace / "cloudflare.ini")
        or any(
            key.endswith("_hook") and value not in ("", "None")
            for key, value in parameters.items()
        )
    ):
        raise ValueError("Unexpected renewal settings")


def main() -> int:
    created = False
    stage = "coordinator and RAM preflight"
    try:
        if len(sys.argv) > 2:
            raise ValueError()
        environment_name = sys.argv[1] if len(sys.argv) == 2 else "staging"
        profile(environment_name)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        os.umask(0o077)
        acme.require_coordinator_hardening()
        fd = os.open(acme.RAM_ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            acme.require_noswap_mount(fd)
        finally:
            os.close(fd)
        stage = "request validation"
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
            stage = "restoring wrapped state"
            restore(
                WORKSPACE,
                base64.b64decode(request["state"], validate=True),
                environment=environment_name,
            )
            stage = "checking recovered renewal configuration"
            check_renewal_config(WORKSPACE, environment_name)
            stage = "inspecting recovered certificate and key"
            before, key = acme.inspect_certificate(
                WORKSPACE, allow_expired=environment_name == "production"
            )
            if environment_name == "production":
                stage = "verifying recovered production trust"
                verify_production(WORKSPACE, allow_expired=True)
            accounts = {
                p.relative_to(WORKSPACE): p.read_bytes()
                for p in (WORKSPACE / "config/accounts").rglob("private_key.json")
            }
            if len(accounts) != 1:
                raise ValueError()
        else:
            before, key = b"", b""
        stage = "preparing the RAM credentials file"
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
            f"Checking recovered {environment_name} state for renewal."
            if recovered
            else f"Issuing fresh {environment_name} state.",
            file=sys.stderr,
            flush=True,
        )
        stage = "Certbot renewal check" if recovered else "Certbot issuance"
        subprocess.run(
            command(WORKSPACE, email, renew=recovered, environment=environment_name),
            cwd=WORKSPACE,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=acme.CERTBOT_TIMEOUT,
        )
        stage = "inspecting issued certificate and key"
        print(
            "Inspecting the resulting certificate and key.", file=sys.stderr, flush=True
        )
        after, new_key = acme.inspect_certificate(WORKSPACE)
        stage = "checking issued renewal configuration"
        print(
            "Checking the resulting Certbot renewal configuration.",
            file=sys.stderr,
            flush=True,
        )
        check_renewal_config(WORKSPACE, environment_name)
        if environment_name == "production":
            stage = "verifying issued production trust"
            print(
                "Verifying the resulting production certificate chain.",
                file=sys.stderr,
                flush=True,
            )
            verify_production(WORKSPACE)
            print(
                "PASS: production certificate name, key, validity and system-trusted chain verified.",
                file=sys.stderr,
                flush=True,
            )
        stage = "checking account and TLS key continuity"
        after_accounts = {
            p.relative_to(WORKSPACE): p.read_bytes()
            for p in (WORKSPACE / "config/accounts").rglob("private_key.json")
        }
        if recovered and (
            (environment_name == "staging" and before == after)
            or key != new_key
            or after_accounts != accounts
        ):
            raise ValueError()
        if recovered and environment_name == "production":
            print(
                "PASS: reused existing production certificate; renewal was not due."
                if before == after
                else "PASS: renewed production certificate with the existing account and TLS key.",
                file=sys.stderr,
                flush=True,
            )
        stage = "serializing verified state"
        sys.stdout.buffer.write(snapshot(WORKSPACE, environment=environment_name))
        sys.stdout.buffer.flush()
    except acme.RehearsalError as exc:
        print(f"ACME state operation failed during {stage}: {exc}", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired as exc:
        print(
            f"ACME state operation timed out during {stage} after {exc.timeout} seconds.",
            file=sys.stderr,
        )
        return 1
    except subprocess.CalledProcessError as exc:
        print(
            f"ACME state operation failed during {stage} with exit status {exc.returncode}.",
            file=sys.stderr,
        )
        return 1
    except Exception:
        print(
            f"ACME state operation failed during {stage}; private details suppressed.",
            file=sys.stderr,
        )
        return 1
    finally:
        # The transient service's private mount is destroyed even on termination.
        if created:
            shutil.rmtree(WORKSPACE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
