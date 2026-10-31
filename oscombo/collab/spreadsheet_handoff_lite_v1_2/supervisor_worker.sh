#!/usr/bin/env bash
# Runs in its own detached session. A stop request drains the current arm.
set -u
mode="${1:-}"
dir="${CODESK_CASE6_SUPERVISOR_DIR:?Missing supervisor directory}"
stop_file="${CODESK_CASE6_STOP_FILE:?Missing stop request path}"
case "$mode" in
    controls) script=oscombo/collab/spreadsheet_handoff_lite_v1_2/run_guest_controls.sh; args=() ;;
    pilot|triad1|triad2|triad3) script=oscombo/collab/spreadsheet_handoff_lite_v1_2/run_model.sh; args=("$mode") ;;
    *) echo 'Invalid Case 6 supervisor mode.' >&2; exit 3 ;;
esac
record_exit() {
    local code="$1"
    printf '%s\n' "$code" > "$dir/exit-code.txt.tmp"
    mv "$dir/exit-code.txt.tmp" "$dir/exit-code.txt"
}
request_drain() {
    if [[ ! -e "$stop_file" ]]; then
        printf '{"source":"supervisor-signal","requested_utc":"%s"}\n' "$(date -u +%FT%TZ)" > "$stop_file.tmp"
        mv "$stop_file.tmp" "$stop_file"
    fi
    echo 'Stop requested: current arm continues to its cleanup; no later arm will start.' >&2
}
trap 'record_exit "$?"' EXIT
trap request_drain TERM INT
bash "$script" "${args[@]}" &
runner=$!
ticks="$(awk '{print $22}' "/proc/$runner/stat" 2>/dev/null || true)"
boot="$(cat /proc/sys/kernel/random/boot_id)"
printf '{"runner_pid":%s,"start_ticks":"%s","boot_id":"%s"}\n' "$runner" "$ticks" "$boot" > "$dir/runner.json.tmp"
mv "$dir/runner.json.tmp" "$dir/runner.json"
while :; do
    if wait "$runner"; then code=0; else code=$?; fi
    # wait can be interrupted by a signal while the current arm is still live.
    if kill -0 "$runner" 2>/dev/null; then continue; fi
    break
done
printf '%s\n' "$code" > "$dir/runner-exit-code.txt"
exit "$code"
