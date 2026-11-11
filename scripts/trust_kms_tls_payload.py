"""Extract only TLS PEMs from the authenticated production snapshot in memory."""

import base64
import json
import posixpath
from typing import cast

from trust_kms_acme_profile import profile
from trust_kms_acme_state import LIMIT


def payload(encoded: bytes, instance: str) -> bytes:
    if len(encoded) > LIMIT:
        raise ValueError()
    value = json.loads(encoded)
    if value["format"] != profile("production").format:
        raise ValueError()
    entries = cast(dict[str, dict[str, str]], value["entries"])

    def read(name: str) -> bytes:
        for _ in range(32):
            if (
                name.startswith("/")
                or name == ".."
                or name.startswith("../")
                or posixpath.normpath(name) != name
            ):
                raise ValueError()
            entry = entries[name]
            if set(entry) == {"data"}:
                return base64.b64decode(entry["data"], validate=True)
            if set(entry) != {"link"} or entry["link"].startswith("/"):
                raise ValueError()
            name = posixpath.normpath(
                posixpath.join(posixpath.dirname(name), entry["link"])
            )
        raise ValueError()

    directory = "live/kms.k8s-aux.simlun.se/"
    return json.dumps(
        {
            "expected_instance": instance,
            "private_key": base64.b64encode(read(directory + "privkey.pem")).decode(),
            "certificate": base64.b64encode(read(directory + "fullchain.pem")).decode(),
        }
    ).encode()
