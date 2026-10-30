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

stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
manifest="audits/three_lite_cases_20261029/case7-v1p2-controls-${stamp}.tsv"
printf 'control\tcondition\trun_id\texit_code\tstatus\tverdict\tfree_kib\tactive_guest_count\n' > "$manifest"
min_free_kib=$((15 * 1024 * 1024))
for entry in 'positive shared' 'positive isolated' 'negative shared' 'negative isolated'; do
    read -r control side <<< "$entry"
    run_id="wa-lite-v1p2-scripted-${control}-${side}-${stamp}"
    run_root="runs/${run_id}"
    log="audits/three_lite_cases_20261029/${run_id}-driver.log"
    free_kib=$(df -Pk "$PWD" 2>/dev/null | awk 'NR==2 {print $4}') || free_kib=""
    if [[ ! "$free_kib" =~ ^[0-9]+$ ]] || (( free_kib < min_free_kib )); then
        status=NOT_STARTED_LOW_DISK
        [[ "$free_kib" =~ ^[0-9]+$ ]] || status=NOT_STARTED_DISK_CHECK_ERROR
        printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
            "$control" "$side" "$run_id" '-' "$status" NOT_STARTED "$free_kib" '-' >> "$manifest"
        echo "${status}: ${run_id}; free_kib=${free_kib:-unknown}; required_kib=${min_free_kib}; manifest=${manifest}" >&2
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
        printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
            "$control" "$side" "$run_id" '-' "$status" NOT_STARTED "$free_kib" "$active_guest_count" >> "$manifest"
        echo "${status}: ${run_id}; active_guest_count=${active_guest_count}; manifest=${manifest}" >&2
        exit 3
    fi
    negative_flag=()
    [[ "$control" == "negative" ]] && negative_flag=(--scripted-negative)
    echo "Starting ${run_id} at $(date -u +%FT%TZ)"
    "$osworld_python" \
        -m oscombo.collab.workspace_assembly_lite_v1p2.live_pilot \
        --condition "collaborative_${side}" --run-root "$run_root" \
        --provider "$OSWORLD_DIR" --image "$OSCOMBO_GUEST_IMAGE" \
        --runtime "$OSCOMBO_RUNTIME_IMAGE" "${negative_flag[@]}" > "$log" 2>&1
    exit_code=$?
    status="NO_RESULT"
    if [[ -f "$run_root/result.json" ]]; then
        status=$("$osworld_python" -c \
            'import json,sys; print(json.load(open(sys.argv[1])).get("status","NO_STATUS"))' \
            "$run_root/result.json") || status="UNREADABLE_RESULT"
    fi
    expected_status=PASS
    expected_exit=0
    if [[ "$control" == "negative" ]]; then
        expected_status=FAIL
        expected_exit=2
    fi
    verdict=EXPECTED
    if [[ "$status" != "$expected_status" || "$exit_code" -ne "$expected_exit" ]]; then
        verdict=UNEXPECTED
    fi
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$control" "$side" "$run_id" "$exit_code" "$status" "$verdict" "$free_kib" "$active_guest_count" >> "$manifest"
    echo "Finished ${run_id}: exit ${exit_code}, status ${status}, ${verdict} at $(date -u +%FT%TZ)"
    if [[ "$verdict" == "UNEXPECTED" ]]; then
        echo "Stopped after unexpected control; manifest: ${manifest}" >&2
        exit 1
    fi
done
echo "Manifest: ${manifest}"
