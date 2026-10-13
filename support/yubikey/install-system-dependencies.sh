#!/usr/bin/env bash
set -euo pipefail

install_packages() {
    local package
    local -a missing=()
    local -a packages=(
        python3 python3-venv python3-pip python3-dev
        build-essential swig pkg-config libpcsclite-dev make git udev
    )

    for package in "${packages[@]}"; do
        if [[ "$(dpkg-query -W -f='${db:Status-Status}' "$package" 2>/dev/null || true)" != installed ]]; then
            missing+=("$package")
        fi
    done

    if ((${#missing[@]})); then
        apt-get update
        apt-get install --yes --no-install-recommends "${missing[@]}"
    fi
}

main() {
    # shellcheck source=/dev/null
    source /etc/os-release
    case "${ID:-}" in
        debian|ubuntu) ;;
        *) printf '%s\n' 'This installer supports Debian and Ubuntu.' >&2; return 1 ;;
    esac

    if ((EUID != 0)); then
        exec sudo -- bash "${BASH_SOURCE[0]}"
    fi

    install_packages

    local scope rule
    scope="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
    rule=/etc/udev/rules.d/69-homelab-yubikey.rules
    if ! cmp -s "$scope/69-homelab-yubikey.rules" "$rule"; then
        install -m 0644 "$scope/69-homelab-yubikey.rules" "$rule"
        udevadm control --reload-rules
    fi
    printf '%s\n' 'System dependencies and YubiKey USB permissions are ready.'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
