#!/usr/bin/env bash

case5_require_no_active_oscombo_guests() {
    local active_guests
    if ! active_guests="$(docker ps --filter 'label=oscombo=1' --format '{{.ID}}' 2>&1)"; then
        echo "Docker Guest query failed; refusing to start Case 5: ${active_guests}" >&2
        return 4
    fi
    if [[ -n "$active_guests" ]]; then
        echo "Active oscombo Guest(s); refusing to start Case 5: ${active_guests}" >&2
        return 4
    fi
}
