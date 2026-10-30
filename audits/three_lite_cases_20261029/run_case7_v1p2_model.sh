#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/../.."
if [[ -f env.local.sh ]]; then
    source env.local.sh
elif [[ -f ../CoDesk/env.local.sh ]]; then
    source ../CoDesk/env.local.sh
else
    echo 'Missing env.local.sh for Guest paths' >&2
    exit 3
fi
: "${OSWORLD_DIR:?Set OSWORLD_DIR}"
: "${OSCOMBO_GUEST_IMAGE:?Set OSCOMBO_GUEST_IMAGE}"
: "${OSCOMBO_RUNTIME_IMAGE:?Set OSCOMBO_RUNTIME_IMAGE}"
osworld_python="${OSWORLD_DIR%/}/.venv/bin/python"
if [[ ! -x "$osworld_python" ]]; then
    echo "OSWorld Python is not executable: ${osworld_python}" >&2
    exit 3
fi
: "${AIGCBEST_API_KEY:?Set AIGCBEST_API_KEY in the coordinator environment}"
trap 'unset AIGCBEST_API_KEY' EXIT

arm="${1:-}"
case "$arm" in
    pilot) side=isolated; extra=(--diagnostic-step-limit 12 --model-timeout 600) ;;
    isolated) side=isolated; extra=(--model-timeout 1200) ;;
    shared) side=shared; extra=(--model-timeout 1200) ;;
    shared_lock) side=shared; extra=(--model-timeout 1200 --gui-input-lock) ;;
    *) echo 'Usage: run_case7_v1p2_model.sh pilot|isolated|shared|shared_lock' >&2; exit 2 ;;
esac

stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
run_id="wa-lite-v1p2-${arm}-${stamp}"
run_root="runs/${run_id}"
log="audits/three_lite_cases_20261029/${run_id}-driver.log"
echo "Starting ${run_id} at $(date -u +%FT%TZ)"
"$osworld_python" \
    -m oscombo.collab.workspace_assembly_lite_v1p2.live_pilot \
    --condition "collaborative_${side}" --run-root "$run_root" \
    --provider "$OSWORLD_DIR" --image "$OSCOMBO_GUEST_IMAGE" \
    --runtime "$OSCOMBO_RUNTIME_IMAGE" --model gpt-6-astra \
    --base-url https://api.haogpt.net/v1 --api-key-env AIGCBEST_API_KEY \
    --mcp-python "$osworld_python" \
    --yield-wait-lifecycle --actor-mcp-only "${extra[@]}" > "$log" 2>&1 &
driver_pid=$!
for _ in {1..100}; do
    [[ -d "$run_root" ]] && break
    kill -0 "$driver_pid" 2>/dev/null || break
    sleep 0.1
done
sampler_pid=""
if [[ -d "$run_root" ]] && kill -0 "$driver_pid" 2>/dev/null; then
    "$osworld_python" \
        audits/three_lite_cases_20261029/sample_qemu.py "$run_root" \
        --interval 5 --max-seconds 3600 \
        > "audits/three_lite_cases_20261029/${run_id}-qemu-sampler.log" 2>&1 &
    sampler_pid=$!
fi
wait "$driver_pid"
exit_code=$?
if [[ -n "$sampler_pid" ]]; then
    kill "$sampler_pid" 2>/dev/null || true
    wait "$sampler_pid" 2>/dev/null || true
fi
if [[ -s "$run_root/qemu_process_resources.jsonl" ]]; then
    "$osworld_python" \
        audits/three_lite_cases_20261029/summarize_qemu.py "$run_root" \
        > "audits/three_lite_cases_20261029/${run_id}-qemu-metrics.json" 2>&1 || true
fi
if [[ -f "$run_root/actors.jsonl" ]]; then
    "$osworld_python" \
        audits/lite_v2_lifecycle_20261028/summarize_lifecycle.py "$run_root" \
        > "audits/three_lite_cases_20261029/${run_id}-metrics.log" 2>&1 || true
fi
echo "Finished ${run_id} with exit ${exit_code} at $(date -u +%FT%TZ)"
exit "$exit_code"
