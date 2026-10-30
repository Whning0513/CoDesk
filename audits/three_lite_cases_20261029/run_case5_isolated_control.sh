#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/../.."
source env.local.sh

available_bytes="$(df -PB1 . | awk 'NR==2 {print $4}')"
if (( available_bytes < 15 * 1024 * 1024 * 1024 )); then
    echo "Insufficient disk for two new Guests: ${available_bytes} bytes available" >&2
    exit 4
fi
blender_bin="/data3/whn/Project2/.codesk-deps/blender-5.0.0/blender-5.0.0-linux-x64/blender"
test -x "$blender_bin" || { echo "Host Blender scorer is unavailable" >&2; exit 3; }

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
run_id="mar-lite-v1-scripted-isolated-revert-${stamp}"
run_root="runs/${run_id}"
log="audits/three_lite_cases_20261029/${run_id}-driver.log"
echo "Starting ${run_id} at $(date -u +%FT%TZ)"
/data3/whn/Project2/OSWorld-V2/.venv/bin/python \
    -m oscombo.collab.model_and_review_lite_v1.live_pilot \
    --condition collaborative_isolated --run-root "$run_root" \
    --provider "$OSWORLD_DIR" --image "$OSCOMBO_GUEST_IMAGE" \
    --runtime "$OSCOMBO_RUNTIME_IMAGE" --blender-bin "$blender_bin" \
    > "$log" 2>&1
exit_code=$?
printf 'run_id\texit_code\n%s\t%s\n' "$run_id" "$exit_code" \
    > "audits/three_lite_cases_20261029/case5-isolated-control-${stamp}.tsv"
echo "Finished ${run_id} with exit ${exit_code} at $(date -u +%FT%TZ)"
exit "$exit_code"
