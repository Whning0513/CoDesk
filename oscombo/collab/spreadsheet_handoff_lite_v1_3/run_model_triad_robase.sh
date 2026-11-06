#!/usr/bin/env bash
set +x
set -euo pipefail
case6_v13_dir="$(cd "$(dirname "$0")" && pwd)"
case6_root="$(cd "$case6_v13_dir/../../.." && pwd)"
case6_root_real="$(realpath -e "$case6_root")"
[[ "$case6_root_real" == /data2/* ]] || {
    echo 'The independent v1.3 Git checkout must resolve under /data2.' >&2; exit 3;
}
case6_root="$case6_root_real"
cd "$case6_root"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$case6_root${PYTHONPATH:+:$PYTHONPATH}"

: "${CODESK_CASE6_V13_FROZEN_COMMIT:?Set the reviewed v1.3 source commit}"
: "${CODESK_CASE6_V13_RUN_BASE:?Set a new run directory on /data2}"
: "${CODESK_CASE6_V13_DOCKER_DATA_ROOT:?Set the expected dedicated Docker data-root on /data2}"
: "${CODESK_CASE6_V13_RUNTIME_IMAGE_ID:?Set the expected sha256 image ID of the runtime image}"
: "${CODESK_GUEST_WINDOW_ASSIGNED:?A coordinator must assign the Guest slot}"
: "${OSWORLD_DIR:?Set OSWORLD_DIR}"
: "${OSCOMBO_GUEST_IMAGE:?Set OSCOMBO_GUEST_IMAGE}"
: "${OSCOMBO_RUNTIME_IMAGE:?Set OSCOMBO_RUNTIME_IMAGE}"
: "${CODESK_CASE6_V13_GUEST_IMAGE_SHA256:?Set the frozen Guest image SHA-256}"
: "${CODESK_CASE6_V13_MODEL:?Set the model name once for all arms}"
: "${CODESK_CASE6_V13_BASE_URL:?Set the model base URL once for all arms}"
: "${CODESK_CASE6_V13_API_KEY_ENV:?Set the name of the configured credential environment variable}"

[[ "$CODESK_GUEST_WINDOW_ASSIGNED" == "case6-v13" ]] || {
    echo 'Guest slot is not assigned to case6-v13.' >&2; exit 3;
}
[[ "$(git rev-parse HEAD)" == "$CODESK_CASE6_V13_FROZEN_COMMIT" ]] || {
    echo 'Source HEAD differs from the reviewed v1.3 frozen commit.' >&2; exit 3;
}
[[ -z "$(git status --porcelain --untracked-files=all)" ]] || {
    echo 'Frozen source checkout is dirty.' >&2; exit 3;
}
[[ -d "$OSWORLD_DIR" && -r "$OSWORLD_DIR" ]] || { echo 'OSWORLD_DIR is unavailable.' >&2; exit 3; }
case6_python="$OSWORLD_DIR/.venv/bin/python"
[[ -x "$case6_python" ]] || { echo 'OSWorld Python is unavailable.' >&2; exit 3; }
[[ -r "$OSCOMBO_GUEST_IMAGE" ]] || { echo 'Guest image is unreadable.' >&2; exit 3; }
[[ -r "$OSWORLD_DIR/desktop_env/providers" ]] || { echo 'OSWorld provider package is unavailable.' >&2; exit 3; }
[[ -z "${DOCKER_CONTEXT:-}" ]] || {
    echo 'DOCKER_CONTEXT must be unset; use the explicit Docker socket through DOCKER_HOST.' >&2; exit 3;
}
case6_docker_host="${DOCKER_HOST:-unix:///var/run/docker.sock}"
case "$case6_docker_host" in
    unix:///*) case6_docker_socket="${case6_docker_host#unix://}" ;;
    unix://*) echo 'DOCKER_HOST must be an absolute unix:// socket; no daemon was contacted.' >&2; exit 3 ;;
    *) echo 'Only a Unix-socket Docker endpoint is supported; no daemon was contacted.' >&2; exit 3 ;;
esac
[[ -S "$case6_docker_socket" && -r "$case6_docker_socket" && -w "$case6_docker_socket" ]] || {
    echo 'Selected Docker socket is absent or inaccessible; no Guest will be started.' >&2; exit 3;
}
# Keep Docker SDK/provider calls on the exact daemon whose root and image were
# checked above. Command-scoped DOCKER_HOST assignments alone would not reach
# the Python model runner or its Guest provider.
export DOCKER_HOST="$case6_docker_host"
command -v docker >/dev/null || { echo 'Docker CLI is unavailable.' >&2; exit 3; }
case6_actual_data_root="$(DOCKER_HOST="$case6_docker_host" docker info --format '{{.DockerRootDir}}' 2>/dev/null)" || {
    echo 'Read-only DockerRootDir query failed; no Guest will be started.' >&2; exit 3;
}
if ! "$case6_python" -B -c 'import sys; from oscombo.collab.spreadsheet_handoff_lite_v1_3.model_pilot import docker_data_root_matches; sys.exit(0 if docker_data_root_matches(sys.argv[1], sys.argv[2]) else 1)' \
    "$CODESK_CASE6_V13_DOCKER_DATA_ROOT" "$case6_actual_data_root"; then
    echo 'DockerRootDir does not match the expected dedicated /data2 data-root.' >&2; exit 3
fi
[[ "$CODESK_CASE6_V13_RUNTIME_IMAGE_ID" =~ ^sha256:[0-9a-f]{64}$ ]] || {
    echo 'Expected runtime image ID must be a sha256 content ID.' >&2; exit 3;
}
case6_actual_runtime_image_id="$(DOCKER_HOST="$case6_docker_host" docker image inspect \
    --format '{{.Id}}' "$OSCOMBO_RUNTIME_IMAGE" 2>/dev/null)" || {
    echo 'Pinned runtime image is unavailable in the selected Docker daemon.' >&2; exit 3;
}
if ! "$case6_python" -B -c 'import sys; from oscombo.collab.spreadsheet_handoff_lite_v1_3.model_pilot import docker_image_id_matches; sys.exit(0 if docker_image_id_matches(sys.argv[1], sys.argv[2]) else 1)' \
    "$CODESK_CASE6_V13_RUNTIME_IMAGE_ID" "$case6_actual_runtime_image_id"; then
    echo 'Runtime image ID does not match the pinned expected digest.' >&2; exit 3
fi
[[ "$CODESK_CASE6_V13_API_KEY_ENV" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || {
    echo 'API key selector must be an environment variable name.' >&2; exit 3;
}
if [[ -z "${!CODESK_CASE6_V13_API_KEY_ENV:-}" ]]; then
    echo 'Selected API credential environment variable is empty.' >&2; exit 3
fi
case6_run_base_real="$(realpath -m "$CODESK_CASE6_V13_RUN_BASE")"
[[ "$case6_run_base_real" == /data2/* ]] || {
    echo 'Case 6 v1.3 run base must resolve under /data2.' >&2; exit 3;
}
mkdir -p "$CODESK_CASE6_V13_RUN_BASE"
case6_git_common="$(git rev-parse --git-common-dir)"
[[ "$case6_git_common" = /* ]] || case6_git_common="$case6_root/$case6_git_common"
case6_git_common="$(realpath -e "$case6_git_common")"
[[ "$case6_git_common" == /data2/* ]] || {
    echo 'Git common directory must resolve under /data2.' >&2; exit 3;
}
case6_guest_image="$(realpath -e "$OSCOMBO_GUEST_IMAGE")"
[[ -f "$case6_guest_image" && -r "$case6_guest_image" ]] || {
    echo 'Guest image must be a readable regular file.' >&2; exit 3;
}
[[ "$OSCOMBO_GUEST_IMAGE" == "$case6_guest_image" ]] || {
    echo 'Guest image path must be absolute, canonical, and free of symlinks.' >&2; exit 3;
}
export OSCOMBO_GUEST_IMAGE="$case6_guest_image"
[[ -z "$(find "$CODESK_CASE6_V13_RUN_BASE" -mindepth 1 -maxdepth 1 -print -quit)" ]] || {
    echo 'Run base must be empty; use a new directory to preserve history.' >&2; exit 3;
}
case6_fs_manifest="$CODESK_CASE6_V13_RUN_BASE/filesystem_capacity.tsv"
printf 'filesystem\tpath\tavailable_kib\tavailable_inodes\n' > "$case6_fs_manifest"
case6_check_fs() {
    local label="$1" path="$2" blocks inodes
    blocks="$(df -Pk -- "$path" 2>/dev/null | awk 'NR == 2 {print $4}')"
    inodes="$(df -Pi -- "$path" 2>/dev/null | awk 'NR == 2 {print $4}')"
    [[ "$blocks" =~ ^[0-9]+$ && "$inodes" =~ ^[0-9]+$ ]] || {
        echo "Cannot inspect filesystem capacity for $label." >&2; return 1;
    }
    "$case6_python" -B -c 'import sys; from oscombo.collab.spreadsheet_handoff_lite_v1_3.model_pilot import filesystem_capacity_ok; sys.exit(0 if filesystem_capacity_ok(int(sys.argv[1]), int(sys.argv[2])) else 1)' \
        "$blocks" "$inodes" || {
        echo "$label filesystem needs at least 15 GiB and 1024 free inodes (available: ${blocks} KiB, ${inodes} inodes)." >&2
        return 1
    }
    printf '%s\t%s\t%s\t%s\n' "$label" "$path" "$blocks" "$inodes" >> "$case6_fs_manifest"
}
case6_check_fs 'run base' "$CODESK_CASE6_V13_RUN_BASE"
case6_check_fs 'Docker data-root' "$case6_actual_data_root"
case6_check_fs 'Git common directory' "$case6_git_common"
[[ "$CODESK_CASE6_V13_GUEST_IMAGE_SHA256" =~ ^[0-9a-f]{64}$ ]] || {
    echo 'Frozen Guest image SHA-256 is malformed.' >&2; exit 3;
}
case6_guest_image_fingerprint="$($case6_python -B -c 'import json,sys; from oscombo.collab.spreadsheet_handoff_lite_v1_3.resource_gate_amendment import verify_frozen_image_sha256; print(json.dumps(verify_frozen_image_sha256(sys.argv[1], sys.argv[2]), separators=(",", ":")))' \
    "$case6_guest_image" "$CODESK_CASE6_V13_GUEST_IMAGE_SHA256")" || {
    echo 'Guest image could not be matched to the frozen SHA-256.' >&2; exit 3;
}
case6_guest_image_sha_verified="$CODESK_CASE6_V13_GUEST_IMAGE_SHA256"
case6_verify_guest_image_unchanged() {
    "$case6_python" -B -c 'import json,sys; from oscombo.collab.spreadsheet_handoff_lite_v1_3.resource_gate_amendment import verify_image_unchanged; verify_image_unchanged(sys.argv[1], json.loads(sys.argv[2]))' \
        "$case6_guest_image" "$case6_guest_image_fingerprint" || {
        echo 'Guest image metadata changed during the triad.' >&2; return 1;
    }
}
case6_exit_trap() {
    local case6_exit_code=$?
    trap - EXIT
    if ! case6_verify_guest_image_unchanged; then case6_exit_code=3; fi
    exit "$case6_exit_code"
}
trap case6_exit_trap EXIT
printf 'docker_host\t%s\ndocker_data_root\t%s\nruntime_image\t%s\nruntime_image_id\t%s\nguest_image\t%s\nguest_image_sha256_expected\t%s\nguest_image_sha256_verified\t%s\nguest_image_fingerprint\t%s\nguest_image_capacity_policy\tread_only_base_digest_and_mount_check\ngit_common\t%s\npythondontwritebytecode\t1\n' \
    "$case6_docker_host" "$case6_actual_data_root" "$OSCOMBO_RUNTIME_IMAGE" \
    "$case6_actual_runtime_image_id" "$case6_guest_image" \
    "$CODESK_CASE6_V13_GUEST_IMAGE_SHA256" "$case6_guest_image_sha_verified" \
    "$case6_guest_image_fingerprint" "$case6_git_common" > "$CODESK_CASE6_V13_RUN_BASE/resource_preflight.tsv"
case6_stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
case6_manifest="$CODESK_CASE6_V13_RUN_BASE/triad_manifest.tsv"
( set -o noclobber; printf 'arm\trun_id\texit_code\n' > "$case6_manifest" )

for arm in isolated shared sharedlock; do
    case6_check_fs "run base before $arm" "$CODESK_CASE6_V13_RUN_BASE"
    case6_check_fs "Docker data-root before $arm" "$case6_actual_data_root"
    case6_check_fs "Git common directory before $arm" "$case6_git_common"
    run_id="sh-lite-v1p3-${arm}-${case6_stamp}"
    run_root="$CODESK_CASE6_V13_RUN_BASE/$run_id"
    set +e
    "$case6_python" -m oscombo.collab.spreadsheet_handoff_lite_v1_3.model_pilot \
        --arm "$arm" --run-root "$run_root" --provider "$OSWORLD_DIR" \
        --image "$OSCOMBO_GUEST_IMAGE" --runtime "$OSCOMBO_RUNTIME_IMAGE" \
        --model "$CODESK_CASE6_V13_MODEL" --base-url "$CODESK_CASE6_V13_BASE_URL" \
        --api-key-env "$CODESK_CASE6_V13_API_KEY_ENV" --mcp-python "$case6_python" \
        --robase-validation \
        > "$CODESK_CASE6_V13_RUN_BASE/$run_id.runner.log" 2>&1
    code=$?
    set -e
    printf '%s\t%s\t%s\n' "$arm" "$run_id" "$code" >> "$case6_manifest"
    if [[ "$code" != 0 && "$code" != 2 ]]; then
        echo "Stopped after infrastructure/runner error in $run_id; preserved manifest: $case6_manifest" >&2
        exit 3
    fi
done
echo "Triad episodes ended; inspect each run's result and required visual review. Manifest: $case6_manifest"
