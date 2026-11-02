#!/usr/bin/env bash
# Case 1 v2.1: one independently identified Guest episode per invocation.
set -uo pipefail
set +x
cd "$(dirname "$0")/../../.." || exit 3
source "${CODESK_ENV_FILE:-/data3/whn/Project2/CoDesk/env.local.sh}"
unset AIGCBEST_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
export OSCOMBO_GUEST_CPUS=8 OSCOMBO_GUEST_RAM=8G
: "${OSWORLD_DIR:?}" "${OSCOMBO_GUEST_IMAGE:?}" "${OSCOMBO_RUNTIME_IMAGE:?}"
python="$OSWORLD_DIR/.venv/bin/python"
mode="${1:-}"; run_id="${2:-}"
case "$mode" in
  control-shared) side=shared; guests=1; model=0; extra=();;
  control-isolated) side=isolated; guests=2; model=0; extra=();;
  control-negative-shared) side=shared; guests=1; model=0; extra=(--scripted-negative);;
  pilot-isolated) side=isolated; guests=2; model=1; extra=(--diagnostic-step-limit 18 --model-timeout 900);;
  isolated) side=isolated; guests=2; model=1; extra=(--model-timeout 1200);;
  shared) side=shared; guests=1; model=1; extra=(--model-timeout 1200);;
  shared-lock) side=shared; guests=1; model=1; extra=(--model-timeout 1200 --gui-input-lock);;
  *) echo 'Unknown Case 1 run mode' >&2; exit 3;;
esac
[[ "${CODESK_GUEST_WINDOW_ASSIGNED:-}" == case1-v2p1 ]] || { echo 'No Case 1 resource window' >&2; exit 3; }
[[ "$run_id" =~ ^cdd-v2p1-[a-zA-Z0-9_.-]+$ ]] || { echo 'Unsafe run ID' >&2; exit 3; }
[[ ! -e "runs/$run_id" && ! -e "audits/three_lite_cases_20261029/$run_id-driver.log" ]] || exit 3
git diff --quiet && git diff --cached --quiet || { echo 'Commit tracked source before running' >&2; exit 3; }
source_commit=$(git rev-parse HEAD) || exit 3
for path in "$PWD" /data2 /data3; do
  free=$(df -Pk -- "$path" | awk 'NR==2 {print $4}') || exit 3
  [[ "$free" =~ ^[0-9]+$ ]] && (( free >= 15 * 1024 * 1024 )) || { echo "Disk floor failed: $path" >&2; exit 3; }
done
docker info >/dev/null 2>&1 || { echo 'Docker unavailable' >&2; exit 3; }
active=$(docker ps --filter label=oscombo=1 --format '{{.ID}}') || exit 3
[[ -z "$active" ]] || { echo 'Another OSWorld Guest is running' >&2; exit 3; }
existing=$(docker ps -aq --filter "label=oscombo.run=$run_id") || exit 3
[[ -z "$existing" ]] || exit 3
"$python" - <<'PY' || exit 3
import ctypes, os, pathlib, tempfile
libc = ctypes.CDLL(None, use_errno=True)
fd = libc.inotify_init1(os.O_CLOEXEC)
if fd < 0: raise SystemExit(3)
try:
    with tempfile.TemporaryDirectory(prefix='case1-watch-check-') as root:
        for i in range(64):
            path = pathlib.Path(root) / str(i); path.mkdir()
            if libc.inotify_add_watch(fd, os.fsencode(path), 0x100) < 0: raise SystemExit(3)
finally:
    os.close(fd)
PY
root="$PWD/runs/$run_id"; log="$PWD/audits/three_lite_cases_20261029/$run_id-driver.log"
mkdir -p "$PWD/runs" "$(dirname "$log")"
(set -o noclobber; : > "$log") || exit 3
args=(--case-lite-v2-1 --condition "collaborative_$side" --run-root "$root"
      --provider "$OSWORLD_DIR" --image "$OSCOMBO_GUEST_IMAGE" --runtime "$OSCOMBO_RUNTIME_IMAGE")
if (( model )); then
  key_file="${CODESK_CASE1_KEY_FILE:-/data3/whn/Project2/.codesk-secrets/haogpt_20261027.key}"
  [[ -f "$key_file" && "$(stat -c %a "$key_file")" == 600 && "$(stat -c %u "$key_file")" == "$(id -u)" ]] || exit 3
  IFS= read -r credential < "$key_file"; [[ -n "$credential" ]] || exit 3
  args+=(--model gpt-6-astra --effort medium --base-url https://api.haogpt.net/v1
         --api-key-env AIGCBEST_API_KEY --mcp-python "$python" --model-request-retries 2
         --handoff-lifecycle --yield-wait-lifecycle --actor-mcp-only)
fi
args+=("${extra[@]}")
AIGCBEST_API_KEY="${credential:-}" "$python" -c 'import signal,sys; signal.signal(signal.SIGINT, signal.default_int_handler); from oscombo.collab.data_to_deck.live_pilot import main; main(sys.argv[1:])' "${args[@]}" >> "$log" 2>&1 &
driver=$!; unset credential
for _ in {1..100}; do [[ -d "$root" ]] && break; kill -0 "$driver" 2>/dev/null || break; sleep 0.1; done
sampler=''; disk_monitor=''
if [[ -d "$root" ]] && kill -0 "$driver" 2>/dev/null; then
  printf '%s\n' "$source_commit" > "$root/launcher_source_commit.txt"
  "$python" -m oscombo.collab.spreadsheet_handoff_lite_v1_2.sample_resources "$root" --interval 5 --max-seconds 7200 > "$root/resource_sampler.log" 2>&1 & sampler=$!
  (
    while kill -0 "$driver" 2>/dev/null; do
      printf '%s\t' "$(date -u +%s)"
      df -Pk -- /data2 /data3 | awk 'NR>1 {printf "%s%s", $4, (NR==2 ? "\t" : "\n")}'
      sleep 5
    done
  ) > "$root/disk_capacity_samples.tsv" 2>&1 & disk_monitor=$!
fi
if wait "$driver"; then code=0; else code=$?; fi
if [[ -n "$sampler" ]]; then kill "$sampler" 2>/dev/null || true; wait "$sampler" 2>/dev/null || true; fi
if [[ -n "$disk_monitor" ]]; then kill "$disk_monitor" 2>/dev/null || true; wait "$disk_monitor" 2>/dev/null || true; fi
[[ -d "$root" ]] || exit 3
if [[ "$(git rev-parse HEAD)" != "$source_commit" ]] || ! git diff --quiet || ! git diff --cached --quiet; then
  echo 'Source changed during this episode' >&2; code=3
fi
"$python" - "$root/disk_capacity_samples.tsv" <<'PY' || code=3
import sys
from pathlib import Path
p = Path(sys.argv[1])
rows = [line.split() for line in p.read_text().splitlines()] if p.is_file() else []
if not rows or any(len(row) != 3 or not all(value.isdecimal() for value in row)
                   or min(int(row[1]), int(row[2])) < 15 * 1024 * 1024 for row in rows):
    raise SystemExit('dual filesystem monitoring missing, invalid, or below floor')
PY
"$python" -m oscombo.collab.spreadsheet_handoff_lite_v1_2.check_resources "$root" "$guests" > "$root/resource_profile_check.log" 2>&1 || code=3
"$python" -m oscombo.collab.data_to_deck_lite_v2_1.audit_run "$root" > "$root/case1_evidence_audit.json" 2>&1 || code=3
if (( model )); then
  "$python" -m oscombo.collab.spreadsheet_handoff_lite_v1_2.relay_transport "$root" > "$root/relay_transport_audit.log" 2>&1 || code=3
  "$python" audits/three_lite_cases_20261029/audit_actor_tool_boundary.py "$root" > "$root/actor_tool_boundary_audit.json" || code=3
  "$python" - "$root/actor_tool_boundary_audit.json" <<'PY' || code=3
import json,sys
x=json.load(open(sys.argv[1], encoding='utf-8'))
if any(not x['actors'][role]['total_tool_calls'] or
       x['actors'][role]['outside_gui_collaboration_contract'] for role in ('A','B')):
    raise SystemExit('Actor tool boundary invalid')
PY
fi
printf 'run_id=%s\nexit=%s\n' "$run_id" "$code"
exit "$code"
