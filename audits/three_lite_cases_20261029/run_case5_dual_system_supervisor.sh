#!/usr/bin/env bash
# Detached supervisor for the two-Guest screenshot naming control; no model.
set -u
cd "$(dirname "$0")/../.." || exit 3
run_id="${1:-}"
[[ "$run_id" =~ ^case5-dual-system-health-[0-9]{8}T[0-9]{6}Z$ ]] || exit 3
run_root="runs/$run_id"
[[ ! -e "$run_root" ]] || { echo 'run_id already exists' >&2; exit 3; }
prefix="audits/three_lite_cases_20261029/$run_id"
for suffix in supervisor.pid supervisor.json exit-code.txt; do
    [[ ! -e "${prefix}-${suffix}" ]] || { echo 'supervisor evidence exists' >&2; exit 3; }
done
printf '%s\n' "$$" > "${prefix}-supervisor.pid"
ticks="$(awk '{print $22}' "/proc/$$/stat")"
boot_id="$(cat /proc/sys/kernel/random/boot_id)"
commit="$(git rev-parse HEAD)" || exit 3
printf '{"run_id":"%s","supervisor_pid":%s,"start_ticks":%s,"boot_id":"%s","commit":"%s"}\n' \
    "$run_id" "$$" "$ticks" "$boot_id" "$commit" > "${prefix}-supervisor.json"
record_exit() { printf '%s\n' "$1" > "${prefix}-exit-code.txt.tmp"; mv "${prefix}-exit-code.txt.tmp" "${prefix}-exit-code.txt"; }
trap 'record_exit "$?"' EXIT
source env.local.sh || exit 3
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
source audits/three_lite_cases_20261029/case5_resource_gate.sh || exit 3
free_bytes="$(df -PB1 . | awk 'NR==2 {print $4}')"
(( free_bytes >= 15 * 1024 * 1024 * 1024 )) || { echo 'disk below 15 GiB' >&2; exit 4; }
root="$(docker info --format '{{.DockerRootDir}}')" || exit 4
[[ "$root" == '/data3/whn/Project2/.codesk-docker/data' ]] || { echo 'wrong Docker daemon' >&2; exit 4; }
case5_require_no_active_oscombo_guests || exit 4
python='/data3/whn/Project2/OSWorld-V2/.venv/bin/python'
"$python" -u audits/three_lite_cases_20261029/case5_dual_system_screenshot_control.py \
    --run-root "$run_root" > "${prefix}-driver.log" 2>&1 &
driver_pid=$!
sampler_pid=''
on_term() {
    kill -TERM "$driver_pid" 2>/dev/null || true
    wait "$driver_pid" 2>/dev/null || true
    [[ -z "$sampler_pid" ]] || kill -TERM "$sampler_pid" 2>/dev/null || true
    exit 143
}
trap on_term TERM INT
for _ in {1..100}; do
    [[ -d "$run_root" ]] && break
    kill -0 "$driver_pid" 2>/dev/null || break
    sleep 0.1
done
if [[ -d "$run_root" ]] && kill -0 "$driver_pid" 2>/dev/null; then
    "$python" audits/three_lite_cases_20261029/sample_qemu.py "$run_root" --interval 5 --max-seconds 3600 \
        > "${prefix}-qemu-sampler.log" 2>&1 &
    sampler_pid=$!
fi
wait "$driver_pid"
exit_code=$?
if [[ -n "$sampler_pid" ]]; then
    kill -TERM "$sampler_pid" 2>/dev/null || true
    wait "$sampler_pid" 2>/dev/null || true
fi
printf 'run_id=%s driver_pid=%s exit_code=%s\n' "$run_id" "$driver_pid" "$exit_code"
exit "$exit_code"
