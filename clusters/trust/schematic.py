"""Register a public Talos schematic and write its canonical Image Factory ID."""

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

FACTORY = "https://factory.talos.dev/schematics"


def write_id(source: Path) -> Path:
    if source.suffix not in (".yaml", ".yml"):
        raise ValueError("Expected a YAML schematic path")
    request = Request(
        FACTORY, data=source.read_bytes(), headers={"Content-Type": "application/yaml"}
    )
    with urlopen(request, timeout=60) as response:
        data: object = json.load(response)
    match data:
        case {"id": str(identifier)} if re.fullmatch(r"[0-9a-f]{64}", identifier):
            pass
        case _:
            raise ValueError("Image Factory returned an invalid schematic ID")

    target = source.with_suffix(".id")
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="ascii", dir=target.parent, delete=False
    ) as handle:
        temp = Path(handle.name)
    try:
        temp.write_text(identifier + "\n", encoding="ascii")
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("schematic", type=Path)
    args = parser.parse_args()
    try:
        output = write_id(args.schematic)
    except (OSError, ValueError) as exc:
        print(f"Schematic registration failed: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
