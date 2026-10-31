#!/usr/bin/env bash
set -u
case6_script_dir="$(cd "$(dirname "$0")" && pwd)"
source "$case6_script_dir/run_common.sh"
: "${CODESK_CASE6_KEY_FILE:?Set the local provider credential file path}"
if [[ ! -f "$CODESK_CASE6_KEY_FILE" || ! -r "$CODESK_CASE6_KEY_FILE" ]]; then
    echo 'Local provider credential file is unavailable.' >&2; exit 3
fi
key_mode="$(stat -c '%a' "$CODESK_CASE6_KEY_FILE")"
key_uid="$(stat -c '%u' "$CODESK_CASE6_KEY_FILE")"
if [[ ! "$key_mode" =~ ^[0-7]{3,4}$ ]] || (( (8#$key_mode & 077) != 0 )) || [[ "$key_uid" != "$(id -u)" ]]; then
    echo 'Local provider credential file must be owned by this user and private.' >&2; exit 3
fi
IFS= read -r AIGCBEST_API_KEY < "$CODESK_CASE6_KEY_FILE" || [[ -n "${AIGCBEST_API_KEY:-}" ]]
if [[ -z "${AIGCBEST_API_KEY:-}" ]]; then echo 'Local provider credential file is empty.' >&2; exit 3; fi
export AIGCBEST_API_KEY
trap 'unset AIGCBEST_API_KEY' EXIT
: "${CODESK_CASE6_V12_CONTROLS_MANIFEST:?Supply the reviewed four-control manifest}"
"$case6_python" -m oscombo.collab.spreadsheet_handoff_lite_v1_2.verify_controls "$CODESK_CASE6_V12_CONTROLS_MANIFEST" || exit 3
mode="${1:-}"
case "$mode" in
    pilot) arms=(isolated); budget=(--diagnostic-step-limit 18 --model-timeout 900) ;;
    triad1) arms=(isolated shared sharedlock); budget=(--model-timeout 1200) ;;
    triad2) arms=(sharedlock shared isolated); budget=(--model-timeout 1200) ;;
    triad3) arms=(isolated sharedlock shared); budget=(--model-timeout 1200) ;;
    *) echo 'Usage: run_model.sh pilot|triad1|triad2|triad3' >&2; exit 2 ;;
esac
if [[ "$mode" != pilot ]]; then
    : "${CODESK_CASE6_V12_PILOT_RUN:?Supply the reviewed isolated Pilot run directory}"
    : "${CODESK_CASE6_V12_FROZEN_COMMIT:?Supply the exact frozen source commit}"
    "$case6_python" -m oscombo.collab.spreadsheet_handoff_lite_v1_2.verify_pilot "$CODESK_CASE6_V12_PILOT_RUN" || exit 3
    if [[ "$(git rev-parse HEAD)" != "$CODESK_CASE6_V12_FROZEN_COMMIT" ]] || ! git diff-index --quiet HEAD --; then
        echo 'Tracked worktree or source commit differs from the frozen cohort.' >&2; exit 3
    fi
fi
stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
manifest="audits/three_lite_cases_20261029/case6-v1p2-${mode}-${stamp}.tsv"
( set -o noclobber; printf 'mode\tarm\trun_id\texit_code\tdriver_exit_code\n' > "$manifest" ) || exit 3
for arm in "${arms[@]}"; do
    side="$arm"; lock=(); guest_count=1
    if [[ "$arm" == sharedlock ]]; then side=shared; lock=(--gui-input-lock); fi
    [[ "$side" == isolated ]] && guest_count=2
    run_id="sh-lite-v1p2-${mode}-${arm}-${stamp}"
    echo "Starting $run_id"
    if case6_run_case model "collaborative_${side}" "$run_id" "$guest_count" \
       --handoff-lifecycle --yield-wait-lifecycle --actor-mcp-only --codex-compat-relay \
       --model gpt-6-astra --effort medium "${budget[@]}" "${lock[@]}" \
       --base-url https://api.haogpt.net/v1 --api-key-env AIGCBEST_API_KEY \
       --model-request-retries 2 --mcp-python "$case6_python"; then :; else :; fi
    printf '%s\t%s\t%s\t%s\t%s\n' "$mode" "$arm" "$run_id" "$RUN_CASE_CODE" "$RUN_CASE_DRIVER_CODE" >> "$manifest"
    if [[ "$RUN_CASE_CODE" != 0 && "$RUN_CASE_CODE" != 2 ]]; then
        echo "Stopped on infrastructure or observation status $RUN_CASE_CODE; manifest: $manifest" >&2; exit 3
    fi
done
echo "Finished $mode; manifest: $manifest"
