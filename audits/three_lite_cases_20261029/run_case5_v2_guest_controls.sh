#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/../.."
source env.local.sh
export OSCOMBO_GUEST_CPUS=8 OSCOMBO_GUEST_RAM=8G
source audits/three_lite_cases_20261029/case5_resource_gate.sh || exit 3
blender_bin="/data3/whn/Project2/.codesk-deps/blender-5.0.0/blender-5.0.0-linux-x64/blender"
test -x "$blender_bin" || { echo "Host Blender scorer is unavailable" >&2; exit 3; }

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
manifest="audits/three_lite_cases_20261029/case5-v2-guest-controls-${stamp}.tsv"
[[ ! -e "$manifest" ]] || { echo 'Manifest already exists' >&2; exit 3; }
printf 'control\tcondition\trun_id\texit_code\n' > "$manifest"
for entry in 'positive shared' 'positive isolated' 'negative shared' 'negative isolated'; do
    case5_require_capacity || exit 4
    case5_require_no_active_oscombo_guests || exit 4
    read -r control side <<< "$entry"
    run_id="mar-lite-v2-scripted-${control}-${side}-${stamp}"
    run_root="runs/${run_id}"
    log="audits/three_lite_cases_20261029/${run_id}-driver.log"
    [[ ! -e "$run_root" && ! -e "$log" ]] || { echo 'Run ID already exists' >&2; exit 3; }
    echo "Starting ${run_id} at $(date -u +%FT%TZ)"
    negative_flag=()
    [[ "$control" == "negative" ]] && negative_flag=(--scripted-negative)
    /data3/whn/Project2/OSWorld-V2/.venv/bin/python \
        -m oscombo.collab.model_and_review_lite_v2.live_pilot \
        --condition "collaborative_${side}" --run-root "$run_root" \
        --provider "$OSWORLD_DIR" --image "$OSCOMBO_GUEST_IMAGE" \
        --runtime "$OSCOMBO_RUNTIME_IMAGE" --blender-bin "$blender_bin" \
        "${negative_flag[@]}" > "$log" 2>&1
    exit_code=$?
    printf '%s\t%s\t%s\t%s\n' "$control" "$side" "$run_id" "$exit_code" >> "$manifest"
    echo "Finished ${run_id} with exit ${exit_code} at $(date -u +%FT%TZ)"
    if [[ "$control" == positive && "$exit_code" != 0 ]] ||
       [[ "$control" == negative && "$exit_code" != 2 ]]; then
        echo 'Control outcome unexpected; preserve run and stop' >&2
        exit 3
    fi
done
echo "Manifest: ${manifest}"
