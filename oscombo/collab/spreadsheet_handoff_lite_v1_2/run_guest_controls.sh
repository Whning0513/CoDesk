#!/usr/bin/env bash
set -u
case6_script_dir="$(cd "$(dirname "$0")" && pwd)"
source "$case6_script_dir/run_common.sh"
stamp="${CODESK_CASE6_STAMP:-$(date -u +%Y%m%dT%H%M%SZ)-$$}"
[[ "$stamp" =~ ^[0-9]{8}T[0-9]{6}Z-[0-9]+$ ]] || { echo 'Invalid run stamp.' >&2; exit 3; }
manifest="audits/three_lite_cases_20261029/case6-v1p2-controls-${stamp}.tsv"
( set -o noclobber; printf 'control\tcondition\trun_id\texit_code\tdriver_exit_code\n' > "$manifest" ) || exit 3
for entry in 'positive shared' 'positive isolated' 'wrong-units shared' 'wrong-units isolated'; do
    if case6_stop_requested; then echo 'Stop requested; no further control will start.' >&2; exit 143; fi
    read -r control side <<< "$entry"
    run_id="sh-lite-v1p2-${control}-${side}-${stamp}"
    options=(); expected=0; guest_count=1
    if [[ "$control" == wrong-units ]]; then options=(--scripted-negative); expected=2; fi
    [[ "$side" == isolated ]] && guest_count=2
    echo "Starting $run_id"
    if case6_run_case control "collaborative_${side}" "$run_id" "$guest_count" "${options[@]}"; then :; else :; fi
    printf '%s\t%s\t%s\t%s\t%s\n' "$control" "$side" "$run_id" "$RUN_CASE_CODE" "$RUN_CASE_DRIVER_CODE" >> "$manifest"
    if [[ "$RUN_CASE_CODE" == 143 ]] || case6_stop_requested; then
        echo "Stop requested; current run has ended and no further control will start. Manifest: $manifest" >&2; exit 143
    fi
    if [[ "$RUN_CASE_CODE" != "$expected" ]]; then
        echo "Control stopped at $run_id (expected $expected, got $RUN_CASE_CODE); manifest: $manifest" >&2
        exit 3
    fi
done
echo "Controls finished. Inspect latest and stale peer-view screenshots before running verify_controls: $manifest"
