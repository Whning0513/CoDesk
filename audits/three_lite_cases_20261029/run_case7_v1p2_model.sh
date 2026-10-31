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
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
: "${OSWORLD_DIR:?Set OSWORLD_DIR}"
: "${OSCOMBO_GUEST_IMAGE:?Set OSCOMBO_GUEST_IMAGE}"
: "${OSCOMBO_RUNTIME_IMAGE:?Set OSCOMBO_RUNTIME_IMAGE}"
osworld_python="${OSWORLD_DIR%/}/.venv/bin/python"
if [[ ! -x "$osworld_python" ]]; then
    echo "OSWorld Python is not executable: ${osworld_python}" >&2
    exit 3
fi
credential_file="${CODESK_HAOGPT_KEY_FILE:-../.codesk-secrets/haogpt_20261027.key}"
if [[ ! -f "$credential_file" || "$(stat -c %a "$credential_file")" != 600 ||
      "$(stat -c %u "$credential_file")" != "$(id -u)" ]]; then
    echo "Model credential file must exist, be owned by this user and have mode 600: ${credential_file}" >&2
    exit 3
fi
IFS= read -r credential_value < "$credential_file"
: "${credential_value:?Model credential file is empty}"
# Supply the provider key only to the run coordinator. Its relay receives the
# key, while Codex Actor processes explicitly redact this variable. The QEMU
# sampler and metrics commands inherit no provider credential.
unset AIGCBEST_API_KEY
trap 'unset credential_value AIGCBEST_API_KEY' EXIT

arm="${1:-}"
case "$arm" in
    pilot) side=isolated; extra=(--diagnostic-step-limit 12 --model-timeout 600) ;;
    isolated) side=isolated; extra=(--model-timeout 1200) ;;
    shared) side=shared; extra=(--model-timeout 1200) ;;
    shared_lock) side=shared; extra=(--model-timeout 1200 --gui-input-lock) ;;
    *) echo 'Usage: run_case7_v1p2_model.sh pilot|isolated|shared|shared_lock' >&2; exit 2 ;;
esac

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
run_id="wa-lite-v1p2-${arm}-${stamp}"
run_root="runs/${run_id}"
log="audits/three_lite_cases_20261029/${run_id}-driver.log"
source_commit=$(git rev-parse --verify HEAD) || exit 3
min_free_kib=$((15 * 1024 * 1024))
free_kib=$(df -Pk "$PWD" 2>/dev/null | awk 'NR==2 {print $4}') || free_kib=""
if [[ ! "$free_kib" =~ ^[0-9]+$ ]] || (( free_kib < min_free_kib )); then
    status=NOT_STARTED_LOW_DISK
    [[ "$free_kib" =~ ^[0-9]+$ ]] || status=NOT_STARTED_DISK_CHECK_ERROR
    preflight="audits/three_lite_cases_20261029/${run_id}-preflight.tsv"
    printf 'run_id\tstatus\tfree_kib\trequired_kib\n%s\t%s\t%s\t%s\n' \
        "$run_id" "$status" "$free_kib" "$min_free_kib" > "$preflight"
    echo "${status}: ${run_id}; free_kib=${free_kib:-unknown}; required_kib=${min_free_kib}; preflight=${preflight}" >&2
    exit 3
fi
if active_guests=$(docker ps --filter label=oscombo=1 --format '{{.ID}}' 2>/dev/null); then
    active_guest_count=$(printf '%s\n' "$active_guests" | awk 'NF { n++ } END { print n+0 }')
    status=NOT_STARTED_ACTIVE_GUEST
else
    active_guest_count='-'
    status=NOT_STARTED_GUEST_CHECK_ERROR
fi
if [[ "$status" == NOT_STARTED_GUEST_CHECK_ERROR || "$active_guest_count" -ne 0 ]]; then
    preflight="audits/three_lite_cases_20261029/${run_id}-preflight.tsv"
    printf 'run_id\tstatus\tfree_kib\trequired_kib\tactive_guest_count\n%s\t%s\t%s\t%s\t%s\n' \
        "$run_id" "$status" "$free_kib" "$min_free_kib" "$active_guest_count" > "$preflight"
    echo "${status}: ${run_id}; active_guest_count=${active_guest_count}; preflight=${preflight}" >&2
    exit 3
fi
echo "Starting ${run_id} at $(date -u +%FT%TZ)"
printf '%s\n' "$source_commit" > "audits/three_lite_cases_20261029/${run_id}-source-commit.txt"
echo "Source commit: ${source_commit}"
AIGCBEST_API_KEY="$credential_value" "$osworld_python" \
    -m oscombo.collab.workspace_assembly_lite_v1p2.live_pilot \
    --condition "collaborative_${side}" --run-root "$run_root" \
    --provider "$OSWORLD_DIR" --image "$OSCOMBO_GUEST_IMAGE" \
    --runtime "$OSCOMBO_RUNTIME_IMAGE" --model gpt-6-astra \
    --base-url https://api.haogpt.net/v1 --api-key-env AIGCBEST_API_KEY \
    --mcp-python "$osworld_python" \
    --yield-wait-lifecycle --actor-mcp-only "${extra[@]}" > "$log" 2>&1 &
driver_pid=$!
unset credential_value
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
