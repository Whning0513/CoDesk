#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/../.."
if [[ -f env.local.sh ]]; then
    source env.local.sh
else
    source ../CoDesk/env.local.sh
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
manifest="audits/three_lite_cases_20261029/case7-v1p2-controls-${stamp}.tsv"
printf 'control\tcondition\trun_id\texit_code\n' > "$manifest"
for entry in 'positive shared' 'positive isolated' 'negative shared'; do
    read -r control side <<< "$entry"
    run_id="wa-lite-v1p2-scripted-${control}-${side}-${stamp}"
    run_root="runs/${run_id}"
    log="audits/three_lite_cases_20261029/${run_id}-driver.log"
    negative_flag=()
    [[ "$control" == "negative" ]] && negative_flag=(--scripted-negative)
    echo "Starting ${run_id} at $(date -u +%FT%TZ)"
    /data3/whn/Project2/OSWorld-V2/.venv/bin/python \
        -m oscombo.collab.workspace_assembly_lite_v1p2.live_pilot \
        --condition "collaborative_${side}" --run-root "$run_root" \
        --provider "$OSWORLD_DIR" --image "$OSCOMBO_GUEST_IMAGE" \
        --runtime "$OSCOMBO_RUNTIME_IMAGE" "${negative_flag[@]}" > "$log" 2>&1
    exit_code=$?
    printf '%s\t%s\t%s\t%s\n' "$control" "$side" "$run_id" "$exit_code" >> "$manifest"
    echo "Finished ${run_id} with exit ${exit_code} at $(date -u +%FT%TZ)"
done
echo "Manifest: ${manifest}"
