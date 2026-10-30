#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/../../.."
source "${CODESK_ENV_FILE:-/data3/whn/Project2/CoDesk/env.local.sh}"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
manifest="audits/three_lite_cases_20261029/case6-v1p1-controls-${stamp}.tsv"
printf 'control\tcondition\trun_id\texit_code\n' > "$manifest"
for entry in 'positive shared' 'positive isolated' 'wrong-units shared'; do
    read -r control side <<< "$entry"
    run_id="sh-lite-v1p1-scripted-${control}-${side}-${stamp}"
    log="audits/three_lite_cases_20261029/${run_id}-driver.log"
    negative=()
    [[ "$control" == "wrong-units" ]] && negative=(--scripted-negative)
    echo "Starting ${run_id} at $(date -u +%FT%TZ)"
    /data3/whn/Project2/OSWorld-V2/.venv/bin/python \
        -m oscombo.collab.spreadsheet_handoff_lite_v1_1.live_pilot \
        --condition "collaborative_${side}" --run-root "runs/${run_id}" \
        --provider "$OSWORLD_DIR" --image "$OSCOMBO_GUEST_IMAGE" \
        --runtime "$OSCOMBO_RUNTIME_IMAGE" "${negative[@]}" > "$log" 2>&1
    code=$?
    printf '%s\t%s\t%s\t%s\n' "$control" "$side" "$run_id" "$code" >> "$manifest"
    echo "Finished ${run_id} exit=${code} at $(date -u +%FT%TZ)"
done
echo "Manifest: ${manifest}"
