#!/usr/bin/env bash
# Intended to run in a detached session. The inner runner owns all Guest cleanup.
set -u
cd "$(dirname "$0")/../.." || exit 3
stamp="${1:-}"
[[ "$stamp" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || { echo 'Expected YYYYMMDDTHHMMSSZ stamp' >&2; exit 3; }
prefix="audits/three_lite_cases_20261029/case5-triad1-${stamp}"
for suffix in supervisor.pid supervisor.json exit-code.txt; do
    [[ ! -e "${prefix}-${suffix}" ]] || { echo 'Triad evidence already exists' >&2; exit 3; }
done
commit="$(git rev-parse HEAD)" || exit 3
printf '%s\n' "$$" > "${prefix}-supervisor.pid"
ticks="$(awk '{print $22}' "/proc/$$/stat")"
boot_id="$(cat /proc/sys/kernel/random/boot_id)"
printf '{"stamp":"%s","supervisor_pid":%s,"start_ticks":%s,"boot_id":"%s","frozen_commit":"%s"}\n' \
    "$stamp" "$$" "$ticks" "$boot_id" "$commit" > "${prefix}-supervisor.json"
record_exit() {
    local status="$1"
    printf '%s\n' "$status" > "${prefix}-exit-code.txt.tmp"
    mv "${prefix}-exit-code.txt.tmp" "${prefix}-exit-code.txt"
}
trap 'record_exit "$?"' EXIT
export CODESK_TRIAD_STAMP="$stamp" CODESK_FROZEN_COMMIT="$commit"
bash audits/three_lite_cases_20261029/run_case5_model.sh triad1 &
runner_pid=$!
on_term() {
    trap - TERM INT
    kill -TERM "$runner_pid" 2>/dev/null || true
    wait "$runner_pid" 2>/dev/null || true
    exit 143
}
trap on_term TERM INT
wait "$runner_pid"
exit_code=$?
printf 'stamp=%s runner_pid=%s frozen_commit=%s exit_code=%s\n' \
    "$stamp" "$runner_pid" "$commit" "$exit_code"
exit "$exit_code"
