#!/usr/bin/env bash
set -euo pipefail

install_packages() {
    local package
    local -a missing=()
    local -a packages=(
        python3 python3-venv make git
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

    printf '%s\n' 'Offline Python prerequisites ready. Configure local-user OTP access before token use.'

}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
