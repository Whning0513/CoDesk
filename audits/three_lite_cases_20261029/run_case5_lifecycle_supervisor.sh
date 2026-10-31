#!/usr/bin/env bash
# Run under a detached, explicitly monitored session; one real Guest, no model.
set -u
cd "$(dirname "$0")/../.." || exit 3
run_id="${1:-}"
if [[ ! "$run_id" =~ ^case5-lifecycle-health-[0-9]{8}T[0-9]{6}Z$ ]]; then
    echo 'Expected a unique case5-lifecycle-health-YYYYMMDDTHHMMSSZ run_id' >&2
    exit 3
fi
run_root="runs/$run_id"
[[ ! -e "$run_root" ]] || { echo 'run_id already exists' >&2; exit 3; }
supervisor_dir='audits/three_lite_cases_20261029'
pid_file="$supervisor_dir/$run_id-supervisor.pid"
meta_file="$supervisor_dir/$run_id-supervisor.json"
exit_file="$supervisor_dir/$run_id-exit-code.txt"
if [[ -e "$pid_file" || -e "$meta_file" || -e "$exit_file" ]]; then
    echo 'supervisor evidence already exists for this run_id' >&2
    exit 3
fi
printf '%s\n' "$$" > "$pid_file"
start_ticks="$(awk '{print $22}' "/proc/$$/stat")"
boot_id="$(cat /proc/sys/kernel/random/boot_id)"
printf '{"run_id":"%s","supervisor_pid":%s,"start_ticks":%s,"boot_id":"%s"}\n' \
    "$run_id" "$$" "$start_ticks" "$boot_id" > "$meta_file"
record_exit() {
    local status="$1"
    printf '%s\n' "$status" > "$exit_file.tmp"
    mv "$exit_file.tmp" "$exit_file"
}
trap 'record_exit "$?"' EXIT
source env.local.sh || exit 3
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
source audits/three_lite_cases_20261029/case5_resource_gate.sh || exit 3
free_bytes="$(df -PB1 . | awk 'NR==2 {print $4}')"
(( free_bytes >= 15 * 1024 * 1024 * 1024 )) || { echo 'disk below 15 GiB' >&2; exit 4; }
root="$(docker info --format '{{.DockerRootDir}}')" || exit 4
[[ "$root" == '/data3/whn/Project2/.codesk-docker/data' ]] || { echo 'wrong Docker daemon' >&2; exit 4; }
case5_require_no_active_oscombo_guests || exit 4
driver_log="audits/three_lite_cases_20261029/$run_id-driver.log"
sampler_log="audits/three_lite_cases_20261029/$run_id-qemu-sampler.log"
python='/data3/whn/Project2/OSWorld-V2/.venv/bin/python'
"$python" -u audits/three_lite_cases_20261029/case5_guest_lifecycle_smoke.py \
    --run-root "$run_root" --editor-reopen > "$driver_log" 2>&1 &
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
    "$python" audits/three_lite_cases_20261029/sample_qemu.py "$run_root" \
        --interval 5 --max-seconds 3600 > "$sampler_log" 2>&1 &
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
