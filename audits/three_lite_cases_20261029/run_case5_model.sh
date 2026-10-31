#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/../.."
source env.local.sh || exit 3
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
source audits/three_lite_cases_20261029/case5_resource_gate.sh || exit 3
credential_file="${CODESK_MODEL_KEY_FILE:-/data3/whn/Project2/.codesk-secrets/haogpt_20261027.key}"
if [[ ! -r "$credential_file" ]]; then
    echo "Model credential file is not readable: ${credential_file}" >&2
    exit 3
fi
IFS= read -r AIGCBEST_API_KEY < "$credential_file"
: "${AIGCBEST_API_KEY:?Model credential file is empty}"
export AIGCBEST_API_KEY
trap 'unset AIGCBEST_API_KEY' EXIT

mode="${1:-}"
case "$mode" in
    pilot) arms=(isolated); extra=(--diagnostic-step-limit 12 --model-timeout 600) ;;
    triad1) arms=(isolated shared shared_lock); extra=(--model-timeout 1200) ;;
    triad2) arms=(shared_lock shared isolated); extra=(--model-timeout 1200) ;;
    *) echo 'Usage: run_case5_model.sh pilot|triad1|triad2' >&2; exit 2 ;;
esac
blender_bin="/data3/whn/Project2/.codesk-deps/blender-5.0.0/blender-5.0.0-linux-x64/blender"
test -x "$blender_bin" || exit 3
stamp="${CODESK_TRIAD_STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
[[ "$stamp" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || { echo 'Invalid run stamp' >&2; exit 3; }
frozen_commit="${CODESK_FROZEN_COMMIT:-$(git rev-parse HEAD)}"
[[ "$(git rev-parse HEAD)" == "$frozen_commit" ]] || { echo 'Frozen commit mismatch' >&2; exit 3; }
git diff --quiet && git diff --cached --quiet || { echo 'Tracked worktree changes; refusing to start' >&2; exit 3; }
manifest="audits/three_lite_cases_20261029/case5-${mode}-${stamp}.tsv"
[[ ! -e "$manifest" ]] || { echo 'Manifest already exists' >&2; exit 3; }
printf 'mode\tarm\trun_id\texit_code\n' > "$manifest"
printf '{"mode":"%s","stamp":"%s","frozen_commit":"%s","model":"gpt-6-astra","inotify_exhaustion_observed":true}\n' \
    "$mode" "$stamp" "$frozen_commit" > "audits/three_lite_cases_20261029/case5-${mode}-${stamp}-config.json"
driver_pid=''
sampler_pid=''
host_sampler_pid=''
run_id=''
on_term() {
    trap - TERM INT
    if [[ -n "$driver_pid" ]]; then
        kill -TERM "$driver_pid" 2>/dev/null || true
        wait "$driver_pid" 2>/dev/null || true
        printf '%s\t%s\t%s\t%s\n' "$mode" "${arm:-unknown}" "$run_id" 3 >> "$manifest"
    fi
    [[ -z "$sampler_pid" ]] || kill -TERM "$sampler_pid" 2>/dev/null || true
    [[ -z "$host_sampler_pid" ]] || kill -TERM "$host_sampler_pid" 2>/dev/null || true
    echo 'Supervisor interrupted; active arm is infrastructure-invalid and cleanup was requested.' >&2
    exit 143
}
trap on_term TERM INT
for arm in "${arms[@]}"; do
    [[ "$(git rev-parse HEAD)" == "$frozen_commit" ]] && git diff --quiet && git diff --cached --quiet || {
        echo 'Frozen source changed; stopping triad' >&2; exit 3; }
    available_bytes="$(df -PB1 . | awk 'NR==2 {print $4}')"
    if (( available_bytes < 15 * 1024 * 1024 * 1024 )); then
        echo "Stopping before next Guest: disk available ${available_bytes} bytes (<15 GiB)" >&2
        exit 4
    fi
    case5_require_no_active_oscombo_guests || exit 4
    condition="collaborative_${arm%_lock}"
    lock_flag=()
    [[ "$arm" == "shared_lock" ]] && lock_flag=(--gui-input-lock)
    run_id="mar-lite-v1-${mode}-${arm}-${stamp}"
    run_root="runs/${run_id}"
    log="audits/three_lite_cases_20261029/${run_id}-driver.log"
    echo "Starting ${run_id} at $(date -u +%FT%TZ)"
    /data3/whn/Project2/OSWorld-V2/.venv/bin/python \
        audits/three_lite_cases_20261029/case5_signal_safe_module.py \
        oscombo.collab.model_and_review_lite_v1.live_pilot \
        --condition "$condition" --run-root "$run_root" \
        --provider "$OSWORLD_DIR" --image "$OSCOMBO_GUEST_IMAGE" \
        --runtime "$OSCOMBO_RUNTIME_IMAGE" --blender-bin "$blender_bin" \
        --model gpt-6-astra --base-url https://api.haogpt.net/v1 \
        --api-key-env AIGCBEST_API_KEY \
        --mcp-python /data3/whn/Project2/OSWorld-V2/.venv/bin/python \
        --yield-wait-lifecycle --actor-mcp-only "${lock_flag[@]}" "${extra[@]}" \
        > "$log" 2>&1 &
    driver_pid=$!
    for _ in {1..100}; do
        [[ -d "$run_root" ]] && break
        kill -0 "$driver_pid" 2>/dev/null || break
        sleep 0.1
    done
    sampler_pid=""
    host_sampler_pid=""
    if [[ -d "$run_root" ]] && kill -0 "$driver_pid" 2>/dev/null; then
        /data3/whn/Project2/OSWorld-V2/.venv/bin/python \
            audits/three_lite_cases_20261029/sample_qemu.py "$run_root" \
            --interval 5 --max-seconds 3600 \
            > "audits/three_lite_cases_20261029/${run_id}-qemu-sampler.log" 2>&1 &
        sampler_pid=$!
        /data3/whn/Project2/OSWorld-V2/.venv/bin/python \
            audits/three_lite_cases_20261029/sample_case5_host.py "$run_root" \
            --interval 5 --max-seconds 3600 \
            > "audits/three_lite_cases_20261029/${run_id}-host-sampler.log" 2>&1 &
        host_sampler_pid=$!
    fi
    wait "$driver_pid"
    exit_code=$?
    driver_pid=''
    if [[ -n "$sampler_pid" ]]; then
        kill "$sampler_pid" 2>/dev/null || true
        wait "$sampler_pid" 2>/dev/null || true
        sampler_pid=''
    fi
    if [[ -n "$host_sampler_pid" ]]; then
        kill "$host_sampler_pid" 2>/dev/null || true
        wait "$host_sampler_pid" 2>/dev/null || true
        host_sampler_pid=''
    fi
    printf '%s\t%s\t%s\t%s\n' "$mode" "$arm" "$run_id" "$exit_code" >> "$manifest"
    if [[ -s "$run_root/qemu_process_resources.jsonl" ]]; then
        /data3/whn/Project2/OSWorld-V2/.venv/bin/python \
            audits/three_lite_cases_20261029/summarize_qemu.py "$run_root" \
            > "audits/three_lite_cases_20261029/${run_id}-qemu-metrics.json" 2>&1 || true
    fi
    if [[ -f "$run_root/actors.jsonl" ]]; then
        /data3/whn/Project2/OSWorld-V2/.venv/bin/python \
            audits/lite_v2_lifecycle_20261028/summarize_lifecycle.py "$run_root" \
            > "audits/three_lite_cases_20261029/${run_id}-metrics.log" 2>&1 || true
        /data3/whn/Project2/OSWorld-V2/.venv/bin/python \
            -m oscombo.collab.spreadsheet_handoff_lite_v1_1.summarize_lock "$run_root" \
            > "audits/three_lite_cases_20261029/${run_id}-gui-lock.json" 2>&1 || true
        /data3/whn/Project2/OSWorld-V2/.venv/bin/python \
            audits/three_lite_cases_20261029/audit_actor_tool_boundary.py "$run_root" \
            > "audits/three_lite_cases_20261029/${run_id}-tool-boundary.json" 2>&1 || true
    fi
    echo "Finished ${run_id} with exit ${exit_code} at $(date -u +%FT%TZ)"
    if (( exit_code != 0 && exit_code != 2 )); then
        echo "Stopping triad after infrastructure or runner error in ${run_id}" >&2
        exit "$exit_code"
    fi
    if ! /data3/whn/Project2/OSWorld-V2/.venv/bin/python \
        audits/three_lite_cases_20261029/case5_audit_completed_arm.py "$run_root" \
        --exit-code "$exit_code" --condition "$condition" \
        --boundary "audits/three_lite_cases_20261029/${run_id}-tool-boundary.json" \
        --resources "audits/three_lite_cases_20261029/${run_id}-qemu-metrics.json" \
        > "$run_root/completed_arm_audit.json"; then
        echo "Stopping triad: ${run_id} evidence requires review" >&2
        exit 3
    fi
    case5_require_no_active_oscombo_guests || exit 4
done
echo "Manifest: ${manifest}"
