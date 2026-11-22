#!/bin/sh
check_freshness() {
    created=$1
    now=$2
    case "$created" in
        ''|*[!0-9]*) echo "Missing or invalid Raft snapshot timestamp" >&2; return 1 ;;
    esac
    # Epoch seconds for current dates are ten digits. Reject unbounded input
    # before shell arithmetic and use decimal-only values.
    case "$created" in
        0*|???????????*) echo "Invalid Raft snapshot timestamp" >&2; return 1 ;;
    esac
    age=$((now - created))
    if [ "$age" -lt 0 ] || [ "$age" -ge 86400 ]; then
        printf 'Raft snapshot must be less than 24 hours old (age=%ss).\n' "$age" >&2
        return 1
    fi
}
