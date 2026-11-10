"""Issue and renew a disposable Trust KMS certificate on the coordinator."""

import os
import re
import resource
import signal
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

RAM_ROOT = Path("/run/trust-kms-acme")
HOSTNAME = "kms.k8s-aux.simlun.se"
STAGING_CA = "https://acme-staging-v02.api.letsencrypt.org/directory"
CERTBOT_TIMEOUT = 150
TOKEN = re.compile(rb"[A-Za-z0-9_-]{16,128}")
EMAIL = re.compile(r"[A-Za-z0-9_.+%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}")


class RehearsalError(ValueError):
    """A public diagnostic without child output or credentials."""


def require_noswap_mount(fd: int) -> None:
    mount_id = next(
        (
            line.split()[1]
            for line in Path(f"/proc/self/fdinfo/{fd}").read_text().splitlines()
            if line.startswith("mnt_id:")
        ),
        None,
    )
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        before, _, after = line.partition(" - ")
        if before.split()[0] == mount_id:
            filesystem, _source, options = after.split()
            if filesystem == "tmpfs" and "noswap" in options.split(","):
                return
    raise RehearsalError("The ACME workspace must be on a tmpfs mounted with noswap.")


def require_coordinator_hardening() -> None:
    if Path("/proc/sys/kernel/core_pattern").read_text().strip() != "|/bin/false":
        raise RehearsalError(
            "Apply and verify the coordinator's core dump policy first."
        )
    for line in Path("/proc/swaps").read_text().splitlines()[1:]:
        device = line.split()[0]
        if not re.fullmatch(r"/dev/zram[0-9]+", device):
            raise RehearsalError("The coordinator has non-zram swap enabled.")
        backing = Path("/sys/block", Path(device).name, "backing_dev")
        if backing.read_text().strip() != "none":
            raise RehearsalError("The coordinator has zram writeback enabled.")


def certbot_command(workspace: Path, email: str, *, renew: bool) -> list[str]:
    command = [
        "/usr/bin/certbot",
        "--config",
        "/dev/null",
        "--server",
        STAGING_CA,
        "--config-dir",
        str(workspace / "config"),
        "--work-dir",
        str(workspace / "work"),
        "--logs-dir",
        str(workspace / "logs"),
        "--non-interactive",
        "--no-directory-hooks",
        "--cert-name",
        HOSTNAME,
        "--reuse-key",
    ]
    if renew:
        # Certbot otherwise sleeps for up to eight minutes on noninteractive
        # renewal, exceeding this bounded, operator-started rehearsal.
        return [*command, "renew", "--force-renewal", "--no-random-sleep-on-renew"]
    return [
        *command,
        "certonly",
        "--agree-tos",
        "--email",
        email,
        "--dns-cloudflare",
        "--dns-cloudflare-credentials",
        str(workspace / "cloudflare.ini"),
        "--domains",
        HOSTNAME,
    ]


def inspect_certificate(workspace: Path) -> tuple[bytes, bytes]:
    lineage = workspace / "config/live" / HOSTNAME
    certificate = x509.load_pem_x509_certificate((lineage / "cert.pem").read_bytes())
    key = serialization.load_pem_private_key(
        (lineage / "privkey.pem").read_bytes(), password=None
    )
    names = certificate.extensions.get_extension_for_class(
        x509.SubjectAlternativeName
    ).value.get_values_for_type(x509.DNSName)
    now = datetime.now(UTC)
    if (
        names != [HOSTNAME]
        or not certificate.not_valid_before_utc <= now < certificate.not_valid_after_utc
    ):
        raise RehearsalError(
            "The staging certificate has an unexpected name or validity period."
        )
    certificate_key = certificate.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    private_key_public = key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    if certificate_key != private_key_public:
        raise RehearsalError("The staging certificate and private key do not match.")
    return certificate.fingerprint(hashes.SHA256()), certificate_key


def rehearse(workspace: Path, email: str) -> None:
    token = sys.stdin.buffer.read(130).rstrip(b"\n")
    if not TOKEN.fullmatch(token):
        raise RehearsalError("Expected one bounded Cloudflare API token on stdin.")
    (workspace / "cloudflare.ini").write_bytes(
        b"dns_cloudflare_api_token = " + token + b"\n"
    )
    del token
    environment = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(workspace),
        "TMPDIR": str(workspace),
        **{
            f"XDG_{name}_HOME": str(workspace)
            for name in ("CONFIG", "CACHE", "DATA", "STATE")
        },
    }

    def run(renew: bool) -> tuple[bytes, bytes]:
        action = "renewal" if renew else "issuance"
        print(f"Starting Certbot staging {action}.", flush=True)
        try:
            subprocess.run(
                certbot_command(workspace, email, renew=renew),
                cwd=workspace,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=CERTBOT_TIMEOUT,
                check=True,
            )
        except subprocess.TimeoutExpired:
            raise RehearsalError(
                f"Certbot staging {action} timed out after {CERTBOT_TIMEOUT} seconds."
            ) from None
        except subprocess.CalledProcessError as exc:
            raise RehearsalError(
                f"Certbot staging {action} exited with status {exc.returncode}. "
                "Check public DNS, time, and token scope."
            ) from None
        except OSError:
            raise RehearsalError(
                f"Certbot staging {action} could not be started. "
                "Check the installed coordinator tools."
            ) from None
        return inspect_certificate(workspace)

    first, key = run(False)
    renewed, renewed_key = run(True)
    if first == renewed or key != renewed_key:
        raise RehearsalError(
            "Expected a fresh staging certificate with the original TLS key."
        )
    print(
        "PASS: issued and renewed a staging certificate with the same key.", flush=True
    )


def interrupted(_signum: int, _frame: object) -> None:
    raise RehearsalError("ACME rehearsal interrupted.")


def main() -> int:
    if len(sys.argv) != 2 or not EMAIL.fullmatch(sys.argv[1]) or len(sys.argv[1]) > 254:
        print("Supply one public ACME contact email.", file=sys.stderr)
        return 2
    try:
        signal.signal(signal.SIGTERM, interrupted)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        os.umask(0o077)
        print(
            "Checking coordinator hardening and the non-swappable RAM mount.",
            flush=True,
        )
        require_coordinator_hardening()
        fd = os.open(RAM_ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            require_noswap_mount(fd)
            info = os.fstat(fd)
            if info.st_uid != 0 or not info.st_mode & stat.S_ISVTX:
                raise RehearsalError("Expected the isolated root-owned ACME RAM mount.")
            with TemporaryDirectory(prefix="rehearse-", dir=RAM_ROOT) as directory:
                rehearse(Path(directory), sys.argv[1])
        finally:
            os.close(fd)
        print("PASS: removed the disposable ACME workspace.", flush=True)
    except RehearsalError as exc:
        print(exc, file=sys.stderr)
        return 1
    except (OSError, ValueError, x509.ExtensionNotFound):
        print("Protected ACME rehearsal failed. Details suppressed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
