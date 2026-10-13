#!/usr/bin/env bash
set -euo pipefail

# Run from the Ubuntu 26.04 workstation, never on a coordinator.
source /etc/os-release
if [[ "${ID:-}" != ubuntu || "${VERSION_ID:-}" != 26.04 ]]; then
    printf '%s\n' 'This workstation installer targets Ubuntu 26.04.' >&2
    exit 1
fi

if ((EUID != 0)); then
    exec sudo -- bash "${BASH_SOURCE[0]}"
fi

missing=()
for package in ca-certificates make openssh-client python3 python3-venv; do
    if [[ "$(dpkg-query -W -f='${db:Status-Status}' "$package" 2>/dev/null || true)" != installed ]]; then
        missing+=("$package")
    fi
done

if (("${#missing[@]}")); then
    apt-get update
    apt-get install --yes --no-install-recommends "${missing[@]}"
fi
printf '%s\n' 'UPS workstation dependencies are ready.'
