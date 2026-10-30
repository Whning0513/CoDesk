#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/../.."
source "${CODESK_ENV_FILE:-env.local.sh}"
export PYTHONPATH="$PWD:$OSWORLD_DIR"
: "${AIGCBEST_API_KEY:?Set the provider key in the coordinator environment only}"
trap 'unset AIGCBEST_API_KEY' EXIT
python_bin="${CODESK_PYTHON_BIN:-$OSWORLD_DIR/.venv/bin/python}"
mode="${1:-}"
case "$mode" in
    pilot) sides=(isolated) ;;
    triad1) sides=(isolated shared shared_lock) ;;
    triad2) sides=(shared_lock shared isolated) ;;
    *) echo 'Usage: run_v1p6_model.sh pilot|triad1|triad2' >&2; exit 2 ;;
esac

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
manifest="audits/case3_three_arm_20261030/model-${mode}-${stamp}.tsv"
printf 'mode\tarm\trun_id\texit_code\n' > "$manifest"
for side in "${sides[@]}"; do
    free_kib="$(df -Pk . | awk 'NR==2 {print $4}')"
    if (( free_kib < 15 * 1024 * 1024 )); then
        echo "Stopping before $side: less than 15 GiB free" >&2
        exit 4
    fi
    condition="collaborative_${side}"
    lock_flag=()
    if [[ "$side" == shared_lock ]]; then
        condition=collaborative_shared
        lock_flag=(--gui-input-lock)
    fi
    run_id="bv-lite-v1p6-${mode}-${side}-${stamp}"
    run_root="runs/$run_id"
    log="audits/case3_three_arm_20261030/${run_id}-driver.log"
    echo "Starting $run_id at $(date -u +%FT%TZ)"
    "$python_bin" -m oscombo.collab.build_and_verify_lite_v1.live_pilot \
        --condition "$condition" --run-root "$run_root" \
        --provider "$OSWORLD_DIR" --image "$OSCOMBO_GUEST_IMAGE" \
        --runtime "$OSCOMBO_RUNTIME_IMAGE" \
        --model gpt-6-astra --base-url https://api.haogpt.net/v1 \
        --api-key-env AIGCBEST_API_KEY --mcp-python "$python_bin" \
        --model-timeout 1200 --yield-wait-lifecycle --actor-mcp-only \
        "${lock_flag[@]}" > "$log" 2>&1 &
    driver_pid=$!
    for _ in {1..100}; do
        [[ -d "$run_root" ]] && break
        kill -0 "$driver_pid" 2>/dev/null || break
        sleep 0.1
    done
    sampler_pid=""
    if [[ -d "$run_root" ]] && kill -0 "$driver_pid" 2>/dev/null; then
        "$python_bin" audits/three_lite_cases_20261029/sample_qemu.py "$run_root" \
            --interval 5 --max-seconds 3600 \
            > "audits/case3_three_arm_20261030/${run_id}-qemu-sampler.log" 2>&1 &
        sampler_pid=$!
    fi
    wait "$driver_pid"
    exit_code=$?
    if [[ -n "$sampler_pid" ]]; then
        kill "$sampler_pid" 2>/dev/null || true
        wait "$sampler_pid" 2>/dev/null || true
    fi
    printf '%s\t%s\t%s\t%s\n' "$mode" "$side" "$run_id" "$exit_code" >> "$manifest"
    if [[ -s "$run_root/qemu_process_resources.jsonl" ]]; then
        "$python_bin" audits/three_lite_cases_20261029/summarize_qemu.py "$run_root" \
            > "audits/case3_three_arm_20261030/${run_id}-qemu-metrics.json" 2>&1 || true
    fi
    if [[ -f "$run_root/actors.jsonl" ]]; then
        "$python_bin" audits/lite_v2_lifecycle_20261028/summarize_lifecycle.py "$run_root" \
            > "audits/case3_three_arm_20261030/${run_id}-metrics.log" 2>&1 || true
    fi
    echo "Finished $run_id with exit $exit_code at $(date -u +%FT%TZ)"
    if (( exit_code == 3 )); then
        echo "Infrastructure failure; stopping the triad, preserving this run" >&2
        exit 3
    fi
done
echo "Manifest: $manifest"
