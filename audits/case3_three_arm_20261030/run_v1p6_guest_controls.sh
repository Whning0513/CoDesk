#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/../.."
source "${CODESK_ENV_FILE:-env.local.sh}"
export PYTHONPATH="$PWD:$OSWORLD_DIR"
python_bin="${CODESK_PYTHON_BIN:-$OSWORLD_DIR/.venv/bin/python}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
manifest="audits/case3_three_arm_20261030/guest-controls-${stamp}.tsv"
printf 'control\tcondition\trun_id\texit_code\n' > "$manifest"

for entry in 'positive shared' 'positive isolated' 'negative shared'; do
    read -r control side <<< "$entry"
    run_id="bv-lite-v1p6-scripted-${control}-${side}-${stamp}"
    log="audits/case3_three_arm_20261030/${run_id}-driver.log"
    negative_flag=()
    [[ "$control" == negative ]] && negative_flag=(--scripted-negative)
    echo "Starting $run_id at $(date -u +%FT%TZ)"
    "$python_bin" -m oscombo.collab.build_and_verify_lite_v1.live_pilot \
        --condition "collaborative_${side}" --run-root "runs/$run_id" \
        --provider "$OSWORLD_DIR" --image "$OSCOMBO_GUEST_IMAGE" \
        --runtime "$OSCOMBO_RUNTIME_IMAGE" "${negative_flag[@]}" > "$log" 2>&1
    exit_code=$?
    printf '%s\t%s\t%s\t%s\n' "$control" "$side" "$run_id" "$exit_code" >> "$manifest"
    echo "Finished $run_id with exit $exit_code at $(date -u +%FT%TZ)"
done
echo "Manifest: $manifest"
