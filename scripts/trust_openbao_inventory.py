"""Check or seed Trust's OpenBao workload secret inventory."""

import argparse
import json
import re
import secrets as random
import shutil
import subprocess
import sys
from collections.abc import Callable
from contextlib import closing
from http.client import HTTPException, HTTPSConnection
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trust_openbao  # noqa: E402

HOST = "bao.k8s-aux.simlun.se"
MOUNT = "workload-kv"
INVENTORY = trust_openbao.tofu.SCOPE / "openbao/inventory.json"
ZOT_PASSWORD = "trust/zot/publisher-password"
ZOT_VERIFIER = "trust/zot/publisher-verifier"
Api = Callable[[str, str, dict[str, object] | None], object]


class APIError(RuntimeError):
    def __init__(self, status: int) -> None:
        super().__init__(f"OpenBao request failed with HTTP {status}")
        self.status = status


def api(
    token: str, method: str, path: str, payload: dict[str, object] | None
) -> object:
    body = None if payload is None else json.dumps(payload)
    with closing(HTTPSConnection(HOST, timeout=10)) as connection:
        connection.request(
            method,
            f"/v1/{path}",
            body,
            {"X-Vault-Token": token, "Content-Type": "application/json"},
        )
        response = connection.getresponse()
        if response.status not in (200, 204):
            raise APIError(response.status)
        raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError("OpenBao response exceeded the limit")
        return json.loads(raw) if raw else None


def inventory(path: Path) -> dict[str, str]:
    document: object = json.loads(path.read_text())
    match document:
        case {"secrets": entries} if isinstance(entries, list):  # pyright: ignore[reportUnknownVariableType]
            ...
        case _:
            raise ValueError("Invalid OpenBao inventory")
    result: dict[str, str] = {}
    for entry in cast(list[object], entries):
        match entry:
            case {"path": str() as key, "strategy": str() as strategy}:
                if (
                    not re.fullmatch(r"trust/(?:[a-z0-9-]+/)*[a-z0-9-]+", key)
                    or key in result
                    or strategy
                    not in (
                        "generate",
                        "operator-input",
                        "restore",
                        "zot-password",
                        "zot-htpasswd",
                    )
                    or (strategy == "zot-password" and key != ZOT_PASSWORD)
                    or (strategy == "zot-htpasswd" and key != ZOT_VERIFIER)
                ):
                    raise ValueError("Invalid or duplicate OpenBao inventory entry")
                result[key] = strategy
            case _:
                raise ValueError("Invalid OpenBao inventory entry")
    return result


def state(request: Api, key: str) -> str:
    try:
        result = request("GET", f"{MOUNT}/metadata/{key}", None)
    except APIError as error:
        if error.status == 404:
            return "missing"
        raise
    match result:
        case {
            "data": {
                "current_version": int() as version,
                "versions": versions,  # pyright: ignore[reportUnknownVariableType]
            }
        } if version > 0 and isinstance(versions, dict):
            # JSON object keys are strings, including the KV version number.
            current = cast(dict[str, object], versions).get(str(version))
            match current:
                case {"destroyed": False, "deletion_time": ""}:
                    return "present"
                case {"destroyed": bool(), "deletion_time": str()}:
                    return "recover"
                case _:
                    pass
        case {"data": {"current_version": 0}}:
            return "missing"
        case _:
            pass
    raise ValueError("Invalid OpenBao KV metadata")


def zot_password(request: Api) -> str:
    result = request("GET", f"{MOUNT}/data/{ZOT_PASSWORD}", None)
    match result:
        case {"data": {"data": {"value": str() as password}}} if re.fullmatch(
            r"[A-Za-z0-9_-]{43}", password
        ):
            return password
        case _:
            raise ValueError("Invalid Zot publisher password entry")


def zot_verifier(request: Api) -> str:
    htpasswd = shutil.which("htpasswd")
    if htpasswd is None:
        raise ValueError("Missing htpasswd; run make -C clusters/trust tools")
    verifier = subprocess.run(
        [htpasswd, "-niB", "-C", "12", "publisher"],
        input=zot_password(request).encode("ascii") + b"\n",
        capture_output=True,
        check=True,
        timeout=15,
    ).stdout.rstrip(b"\n")
    if not re.fullmatch(rb"publisher:\$2[aby]\$12\$[./A-Za-z0-9]{53}", verifier):
        raise ValueError("htpasswd returned an invalid Zot verifier")
    return verifier.decode("ascii") + "\n"


def populate(request: Api, entries: dict[str, str], *, seed: bool) -> bool:
    ready = True
    for key, strategy in entries.items():
        status = state(request, key)
        if (
            status == "missing"
            and strategy == "zot-password"
            and state(request, ZOT_VERIFIER) != "missing"
        ):
            status = "recover"
        if (
            status == "missing"
            and strategy == "zot-htpasswd"
            and state(request, ZOT_PASSWORD) != "present"
        ):
            status = "waiting-for-password"
        if (
            status == "missing"
            and strategy in ("generate", "zot-password", "zot-htpasswd")
            and seed
        ):
            field, value = (
                ("htpasswd", zot_verifier(request))
                if strategy == "zot-htpasswd"
                else ("value", random.token_urlsafe(32))
            )
            try:
                request(
                    "POST",
                    f"{MOUNT}/data/{key}",
                    {
                        "options": {"cas": 0},
                        "data": {field: value},
                    },
                )
                status = "created"
            except APIError as error:
                # Another seed invocation may have created it first.
                if error.status not in (400, 403) or state(request, key) != "present":
                    raise
                status = "present"
        if status == "missing" and strategy in ("operator-input", "restore"):
            status = strategy
        print(f"{key}: {status}")
        ready = status in ("present", "created") and ready
    return ready


def operator_token(policy: str) -> str:
    helpers = trust_openbao.secrets
    record, key_id = trust_openbao.ROOT_TOKEN
    helpers.require_private_repository(record=record)
    unwrap = helpers.executable(
        Path(sys.executable).with_name("homelab-unwrap"), "homelab-unwrap"
    )
    print(
        "Touch the YubiKey to authorize a short-lived OpenBao token.", file=sys.stderr
    )
    with helpers.hsm_progress_terminal() as terminal:
        root = helpers.recover_bundle(
            unwrap, record=record, key_id=key_id, stderr=terminal
        )
    result = api(
        root.decode("ascii"),
        "POST",
        "auth/token/create",
        {"policies": [policy], "ttl": "5m", "type": "batch", "no_default_policy": True},
    )
    match result:
        case {"auth": {"client_token": str() as token}} if token:
            return token
        case _:
            raise ValueError("OpenBao did not return an inventory token")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "seed", "zot-publisher"))
    args = parser.parse_args()
    try:
        trust_openbao.secrets.harden()
        if args.action == "zot-publisher":
            trust_openbao.secrets.require_pipe()
            token = operator_token("trust-zot-publisher")

            def read_publisher(
                method: str, path: str, payload: dict[str, object] | None
            ) -> object:
                return api(token, method, path, payload)

            print(zot_password(read_publisher))
            return 0
        entries = inventory(INVENTORY)
        token = operator_token(f"trust-workload-{args.action}")

        def request(
            method: str, path: str, payload: dict[str, object] | None
        ) -> object:
            return api(token, method, path, payload)

        return 0 if populate(request, entries, seed=args.action == "seed") else 1
    except APIError as error:
        print(str(error), file=sys.stderr)
    except (ValueError, subprocess.SubprocessError):
        print(
            "OpenBao inventory operation stopped. Check the credential, htpasswd, and the runbook.",
            file=sys.stderr,
        )
    except (HTTPException, OSError, RuntimeError, KeyboardInterrupt):
        print(
            "OpenBao inventory operation stopped. Check setup and the runbook.",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
