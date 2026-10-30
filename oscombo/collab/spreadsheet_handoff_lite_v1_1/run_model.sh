#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/../../.."
source "${CODESK_ENV_FILE:-/data3/whn/Project2/CoDesk/env.local.sh}"
: "${AIGCBEST_API_KEY:?Set the API key in the coordinator environment only}"
trap 'unset AIGCBEST_API_KEY' EXIT

mode="${1:-}"
case "$mode" in
    pilot) arms=(isolated); extra=(--diagnostic-step-limit 12 --model-timeout 600) ;;
    triad1) arms=(isolated shared sharedlock); extra=(--model-timeout 1200) ;;
    triad2) arms=(sharedlock shared isolated); extra=(--model-timeout 1200) ;;
    *) echo 'Usage: run_model.sh pilot|triad1|triad2' >&2; exit 2 ;;
esac
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
manifest="audits/three_lite_cases_20261029/case6-v1p1-${mode}-${stamp}.tsv"
printf 'mode\tarm\trun_id\texit_code\n' > "$manifest"
for arm in "${arms[@]}"; do
    side="$arm"
    lock=()
    if [[ "$arm" == "sharedlock" ]]; then
        side="shared"
        lock=(--gui-input-lock)
    fi
    run_id="sh-lite-v1p1-${mode}-${arm}-${stamp}"
    run_root="runs/${run_id}"
    log="audits/three_lite_cases_20261029/${run_id}-driver.log"
    echo "Starting ${run_id} at $(date -u +%FT%TZ)"
    /data3/whn/Project2/OSWorld-V2/.venv/bin/python \
        -m oscombo.collab.spreadsheet_handoff_lite_v1_1.live_pilot \
        --handoff-lifecycle --actor-mcp-only --codex-compat-relay \
        --condition "collaborative_${side}" "${lock[@]}" \
        --run-root "$run_root" --provider "$OSWORLD_DIR" \
        --image "$OSCOMBO_GUEST_IMAGE" --runtime "$OSCOMBO_RUNTIME_IMAGE" \
        --model gpt-6-astra --effort medium "${extra[@]}" \
        --base-url https://api.haogpt.net/v1 --api-key-env AIGCBEST_API_KEY \
        --model-request-retries 2 \
        --mcp-python /data3/whn/Project2/OSWorld-V2/.venv/bin/python \
        > "$log" 2>&1 &
    driver_pid=$!
    for _ in {1..100}; do
        [[ -d "$run_root" ]] && break
        kill -0 "$driver_pid" 2>/dev/null || break
        sleep 0.1
    done
    sampler_pid=""
    if [[ -d "$run_root" ]] && kill -0 "$driver_pid" 2>/dev/null; then
        /data3/whn/Project2/OSWorld-V2/.venv/bin/python \
            audits/three_lite_cases_20261029/sample_qemu.py "$run_root" \
            --interval 5 --max-seconds 3600 \
            > "audits/three_lite_cases_20261029/${run_id}-qemu-sampler.log" 2>&1 &
        sampler_pid=$!
    fi
    wait "$driver_pid"
    code=$?
    if [[ -n "$sampler_pid" ]]; then
        kill "$sampler_pid" 2>/dev/null || true
        wait "$sampler_pid" 2>/dev/null || true
    fi
    printf '%s\t%s\t%s\t%s\n' "$mode" "$arm" "$run_id" "$code" >> "$manifest"
    if [[ -s "$run_root/qemu_process_resources.jsonl" ]]; then
        /data3/whn/Project2/OSWorld-V2/.venv/bin/python \
            audits/three_lite_cases_20261029/summarize_qemu.py "$run_root" \
            > "audits/three_lite_cases_20261029/${run_id}-qemu-metrics.json" 2>&1 || true
    fi
    if [[ -f "$run_root/actors.jsonl" ]]; then
        /data3/whn/Project2/OSWorld-V2/.venv/bin/python \
            audits/lite_v2_lifecycle_20261028/summarize_lifecycle.py "$run_root" \
            > "audits/three_lite_cases_20261029/${run_id}-metrics.log" 2>&1 || true
    fi
    if [[ -f "$run_root/oracle.json" ]]; then
        /data3/whn/Project2/OSWorld-V2/.venv/bin/python \
            -m oscombo.collab.spreadsheet_handoff_lite_v1_1.audit_handoff "$run_root" \
            > "$run_root/handoff_audit.json" 2>&1 || true
    fi
    if [[ -d "$run_root/actor_runs" ]]; then
        /data3/whn/Project2/OSWorld-V2/.venv/bin/python \
            audits/three_lite_cases_20261029/audit_actor_tool_boundary.py "$run_root" \
            > "$run_root/actor_tool_boundary_audit.json" 2>&1 || true
        /data3/whn/Project2/OSWorld-V2/.venv/bin/python \
            -m oscombo.collab.spreadsheet_handoff_lite_v1_1.summarize_lock "$run_root" \
            > "$run_root/gui_lock_metrics.json" 2>&1 || true
    fi
    echo "Finished ${run_id} exit=${code} at $(date -u +%FT%TZ)"
done
echo "Manifest: ${manifest}"
