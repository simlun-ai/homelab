"""Explicit ACME environments; no caller-supplied CA URLs or storage paths."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Profile:
    name: str
    server: str

    @property
    def key_id(self) -> str:
        return f"homelab/v1/support-aux/acme/{self.name}/r1"

    @property
    def directory(self) -> Path:
        return Path("/var/lib/trust-kms") / f"acme-{self.name}"

    @property
    def filename(self) -> str:
        return f"ups-aux-acme-{self.name}.json"

    @property
    def format(self) -> str:
        return f"trust-acme-{self.name}-v1"


def profile(name: str) -> Profile:
    servers = {
        "staging": "https://acme-staging-v02.api.letsencrypt.org/directory",
        "production": "https://acme-v02.api.letsencrypt.org/directory",
    }
    return Profile(name, servers[name])
