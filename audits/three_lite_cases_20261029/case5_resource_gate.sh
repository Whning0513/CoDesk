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

# A worktree on /data2 still depends on the image, Docker root and shared Git
# object store, which may live on different filesystems. Fail closed for each.
case5_require_capacity() {
    local docker_root git_root image label path free inodes
    image="${OSCOMBO_GUEST_IMAGE:-}"
    [[ -f "$image" ]] || { echo 'Guest image not available' >&2; return 4; }
    docker_root="$(docker info --format '{{.DockerRootDir}}' 2>/dev/null)" || return 4
    git_root="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || return 4
    [[ -n "$docker_root" && -d "$docker_root" && -d "$git_root" ]] || return 4
    for label in run image docker git; do
        case "$label" in
          run) path="$PWD";; image) path="$image";; docker) path="$docker_root";; git) path="$git_root";;
        esac
        free="$(df -PB1 "$path" | awk 'NR==2 {print $4}')" || return 4
        inodes="$(df -Pi "$path" | awk 'NR==2 {print $4}')" || return 4
        if [[ ! "$free" =~ ^[0-9]+$ || ! "$inodes" =~ ^[0-9]+$ ]] ||
           (( free < 15 * 1024 * 1024 * 1024 || inodes < 1024 )); then
            echo "Case 5 ${label} filesystem is below the capacity floor or cannot be checked" >&2
            return 4
        fi
    done
}
