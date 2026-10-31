#!/usr/bin/env bash
# Sourced only by the versioned Case 6 runners. Never print credentials.
set +x
set -u
case6_root="$(git rev-parse --show-toplevel)" || exit 3
cd "$case6_root" || exit 3
source "${CODESK_ENV_FILE:-/data3/whn/Project2/CoDesk/env.local.sh}"
# The model runner loads its provider credential separately from the local
# credential file; scripted controls do not need any provider credential.
unset AIGCBEST_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY GOOGLE_API_KEY
export PYTHONPATH="$case6_root${PYTHONPATH:+:$PYTHONPATH}"
export OSCOMBO_GUEST_CPUS=8
export OSCOMBO_GUEST_RAM=8G
CODESK_CASE6_SOURCE_COMMIT="$(git rev-parse HEAD)" || exit 3
export CODESK_CASE6_SOURCE_COMMIT
if [[ -n "${CODESK_CASE6_SUPERVISOR_COMMIT:-}" && "$CODESK_CASE6_SUPERVISOR_COMMIT" != "$CODESK_CASE6_SOURCE_COMMIT" ]]; then
    echo 'Source changed between supervisor launch and runner startup.' >&2; exit 3
fi
: "${OSWORLD_DIR:?OSWORLD_DIR is required}"
: "${OSCOMBO_GUEST_IMAGE:?OSCOMBO_GUEST_IMAGE is required}"
: "${OSCOMBO_RUNTIME_IMAGE:?OSCOMBO_RUNTIME_IMAGE is required}"
case6_python="$OSWORLD_DIR/.venv/bin/python"
[[ -x "$case6_python" ]] || { echo 'OSWorld Python is unavailable' >&2; exit 3; }
# Coordinator admission only: this does not lock or schedule Actor GUI input.
case6_cohort_lock="/tmp/codesk-case6-v1p2-${UID}.lock"
exec {case6_lock_fd}>"$case6_cohort_lock"
if ! flock -n "$case6_lock_fd"; then echo 'Another Case 6 v1.2 runner owns the cohort slot.' >&2; exit 3; fi

case6_stop_requested() {
    [[ -n "${CODESK_CASE6_STOP_FILE:-}" && -f "$CODESK_CASE6_STOP_FILE" ]]
}

case6_preflight() {
    if [[ "$(git rev-parse HEAD)" != "$CODESK_CASE6_SOURCE_COMMIT" ]] || ! git diff-index --quiet HEAD --; then
        echo 'Case 6 source changed after runner start; refuse a new Guest.' >&2; return 3
    fi
    if [[ "${CODESK_GUEST_WINDOW_ASSIGNED:-}" != case6-v1p2 ]]; then
        echo 'Case 6 Guest resource window is not assigned by the coordinator.' >&2; return 3
    fi
    "$case6_python" -c 'import inspect; from oscombo.collab.data_to_deck.workspace_bridge import SavedArtifactBridge; assert "peer_view_dirs" in inspect.signature(SavedArtifactBridge).parameters and hasattr(SavedArtifactBridge,"diagnostics")' || return 3
    local available
    available="$(df -Pk "$case6_root" | awk 'NR == 2 {print $4}')"
    if [[ ! "$available" =~ ^[0-9]+$ ]] || (( available < 15 * 1024 * 1024 )); then
        echo "Case 6 needs at least 15 GiB free; available ${available:-unknown} KiB." >&2; return 3
    fi
    if ! docker info >/dev/null 2>&1; then echo 'Dedicated Docker is unavailable.' >&2; return 3; fi
    if pgrep -af '^qemu-system-x86_64' >/dev/null ||
       [[ -n "$(docker ps --filter label=oscombo=1 --format '{{.ID}}' 2>/dev/null)" ]]; then
        echo 'Another QEMU/OSWorld Guest is active; stop before starting a new run.' >&2; return 3
    fi
}

# run_case ROLE CONDITION RUN_ID EXPECTED_GUESTS [runner flags ...]
# RUN_CASE_CODE is the raw runner status, or 3 if resource evidence is incomplete.
case6_run_case() {
    local role="$1" condition="$2" run_id="$3" guest_count="$4"
    shift 4
    local root="runs/$run_id" log="audits/three_lite_cases_20261029/${run_id}-driver.log"
    local sampler="" driver code sampler_code
    if case6_stop_requested; then RUN_CASE_DRIVER_CODE=NOT_STARTED; RUN_CASE_CODE=143; return 143; fi
    if ! case6_preflight; then RUN_CASE_DRIVER_CODE=NOT_STARTED; RUN_CASE_CODE=3; return 3; fi
    if case6_stop_requested; then RUN_CASE_DRIVER_CODE=NOT_STARTED; RUN_CASE_CODE=143; return 143; fi
    if [[ "$role" == model ]]; then export AIGCBEST_API_KEY; fi
    "$case6_python" -m oscombo.collab.spreadsheet_handoff_lite_v1_2.live_pilot \
        --condition "$condition" --run-root "$root" --provider "$OSWORLD_DIR" \
        --image "$OSCOMBO_GUEST_IMAGE" --runtime "$OSCOMBO_RUNTIME_IMAGE" "$@" \
        > "$log" 2>&1 &
    driver=$!
    # Keep the provider key out of sampler, audit and later helper processes.
    if [[ "$role" == model ]]; then export -n AIGCBEST_API_KEY; fi
    if [[ -n "${CODESK_CASE6_SUPERVISOR_DIR:-}" && -d "$CODESK_CASE6_SUPERVISOR_DIR" ]]; then
        local ticks boot tmp
        ticks="$(awk '{print $22}' "/proc/$driver/stat" 2>/dev/null || true)"
        boot="$(cat /proc/sys/kernel/random/boot_id)"
        tmp="$CODESK_CASE6_SUPERVISOR_DIR/current-driver.json.tmp"
        printf '{"run_id":"%s","driver_pid":%s,"start_ticks":"%s","boot_id":"%s"}\n' \
            "$run_id" "$driver" "$ticks" "$boot" > "$tmp"
        mv "$tmp" "$CODESK_CASE6_SUPERVISOR_DIR/current-driver.json"
    fi
    for _ in {1..100}; do
        [[ -d "$root" ]] && break
        kill -0 "$driver" 2>/dev/null || break
        sleep 0.1
    done
    if [[ -d "$root" ]] && kill -0 "$driver" 2>/dev/null; then
        "$case6_python" -m oscombo.collab.spreadsheet_handoff_lite_v1_2.sample_resources \
            "$root" --interval 5 --max-seconds 5400 > "${root}/resource_sampler.log" 2>&1 &
        sampler=$!
    fi
    if wait "$driver"; then code=0; else code=$?; fi
    if [[ -n "$sampler" ]]; then
        # The driver has finished exact run-owned cleanup; do not touch other processes.
        if kill -0 "$sampler" 2>/dev/null; then kill "$sampler" 2>/dev/null || true; fi
        if wait "$sampler"; then sampler_code=0; else sampler_code=$?; fi
    fi
    RUN_CASE_DRIVER_CODE="$code"
    RUN_CASE_CODE="$code"
    if [[ ! -d "$root" ]]; then
        RUN_CASE_CODE=3
        echo "Run root missing for $run_id; preserve runner status for review." >&2
    elif ! "$case6_python" -m oscombo.collab.spreadsheet_handoff_lite_v1_2.check_resources \
        "$root" "$guest_count" > "${root}/resource_profile_check.log" 2>&1; then
        RUN_CASE_CODE=3
        echo "Resource observation incomplete for $run_id; preserve result for infrastructure review." >&2
    fi
    if [[ "$role" == model && -d "$root/actor_runs" ]]; then
        "$case6_python" -m oscombo.collab.spreadsheet_handoff_lite_v1_2.audit_handoff "$root" > "$root/handoff_audit.json" 2>&1 || true
        "$case6_python" audits/three_lite_cases_20261029/audit_actor_tool_boundary.py "$root" > "$root/actor_tool_boundary_audit.json" 2>&1 || true
        "$case6_python" -m oscombo.collab.spreadsheet_handoff_lite_v1_1.summarize_lock "$root" > "$root/gui_lock_metrics.json" 2>&1 || true
        "$case6_python" audits/lite_v2_lifecycle_20261028/summarize_lifecycle.py "$root" > "$root/model_metrics.log" 2>&1 || true
    fi
    return "$RUN_CASE_CODE"
}
