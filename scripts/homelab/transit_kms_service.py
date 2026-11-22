"""Run the Talos KMS adapter with a projected Kubernetes service identity."""

import json
import os
import re
import signal
import ssl
import sys
from contextlib import closing
from http.client import HTTPException, HTTPSConnection
from ipaddress import IPv6Address, ip_address
from pathlib import Path
from threading import Event
from urllib.parse import unquote, urlsplit
from uuid import UUID

from .transit_kms import TransitKMS, TransitUnavailable, listen_tls


class KubernetesLogin:
    def __init__(self, origin: str, role: str, jwt_path: Path) -> None:
        self._url = urlsplit(origin)
        self._role = role
        self._jwt_path = jwt_path

    def __call__(self) -> str:
        host = self._url.hostname
        assert host is not None
        try:
            jwt = self._jwt_path.read_text(encoding="ascii").strip()
            with closing(
                HTTPSConnection(host, self._url.port, timeout=3)
            ) as connection:
                connection.request(
                    "POST",
                    "/v1/auth/talos-kms/login",
                    json.dumps({"role": self._role, "jwt": jwt}),
                    {"Content-Type": "application/json"},
                )
                response = connection.getresponse()
                if response.status != 200:
                    raise TransitUnavailable("OpenBao Kubernetes login failed")
                document = response.read(8193)
            if len(document) > 8192:
                raise TransitUnavailable("Oversized OpenBao Kubernetes login response")
            result: object = json.loads(document)
        except (OSError, HTTPException, ValueError):
            raise TransitUnavailable("OpenBao Kubernetes login failed") from None
        match result:
            case {"auth": {"client_token": str() as token}} if re.fullmatch(
                r"[!-~]{1,1024}", token
            ):
                return token
            case _:
                raise TransitUnavailable("Invalid OpenBao Kubernetes login response")


def registered_nodes(raw: str) -> dict[str, str]:
    result: object = json.loads(raw)
    if not isinstance(result, dict) or not result:
        raise ValueError("Configure at least one Talos node")
    nodes: dict[str, str] = {}
    for node, address in result.items():  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(node, str) or not isinstance(address, str):
            raise ValueError("Invalid Talos node registration")
        if str(UUID(node)) != node or str(ip_address(address)) != address:
            raise ValueError("Node UUID and address must be canonical")
        if address in nodes.values():
            raise ValueError("Duplicate Talos node address")
        nodes[node] = address
    return nodes


def allows_peer(nodes: dict[str, str], peer: str, node: str) -> bool:
    family, _, address = unquote(peer).partition(":")
    if family not in ("ipv4", "ipv6"):
        return False
    host, separator, port = address.rpartition(":")
    if not separator or not port.isdecimal():
        return False
    try:
        source = ip_address(host.removeprefix("[").removesuffix("]"))
    except ValueError:
        return False
    if isinstance(source, IPv6Address) and source.ipv4_mapped is not None:
        source = source.ipv4_mapped
    return nodes.get(node) == str(source)


def tls_pair(directory: Path) -> tuple[bytes, bytes]:
    # Resolve the projected generation once so rotation cannot mix key and cert.
    generation = (directory / "..data").resolve(strict=True)
    return (generation / "tls.key").read_bytes(), (generation / "tls.crt").read_bytes()


def main() -> int:
    try:
        origin = os.environ["OPENBAO_ADDR"]
        cluster = os.environ["KMS_CLUSTER"]
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,30}", cluster):
            raise ValueError("Invalid cluster name")
        nodes = registered_nodes(os.environ["KMS_NODES"])
        role = f"talos-{cluster}"
        login = KubernetesLogin(origin, role, Path("/var/run/openbao/token"))
        adapter = TransitKMS(
            origin, role, nodes, login, tls=ssl.create_default_context()
        )
        directory = Path("/var/run/kms-tls")
        key, cert = tls_pair(directory)
        stopping = Event()

        def stop(_signal: int, _frame: object) -> None:
            stopping.set()

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        with listen_tls(
            adapter,
            address="[::]:8443",
            private_key=key,
            certificate=cert,
            allows_peer=lambda peer, node: allows_peer(nodes, peer, node),
            reload_certificate=lambda: tls_pair(directory),
        ):
            print("Talos KMS is listening.", flush=True)
            stopping.wait()
    except (KeyError, OSError, RuntimeError, ValueError):
        print(
            "Talos KMS could not start. Check configuration and TLS files.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
