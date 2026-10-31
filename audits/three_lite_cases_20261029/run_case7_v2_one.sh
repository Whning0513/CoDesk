#!/usr/bin/env bash
# One preregistered Case 7 v2 slot; coordinator owns ordering and resource scheduling.
set -uo pipefail
cd "$(dirname "$0")/../.."
if [[ -f env.local.sh ]]; then
    source env.local.sh
elif [[ -f ../CoDesk/env.local.sh ]]; then
    source ../CoDesk/env.local.sh
else
    echo 'Missing env.local.sh for OSWorld paths' >&2
    exit 3
fi
# The provider credential is read only from the owner-only file below. Do not
# inherit unrelated API keys from the invoking shell into the coordinator.
unset AIGCBEST_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY HAOGPT_API_KEY
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
export OSCOMBO_GUEST_CPUS=8 OSCOMBO_GUEST_RAM=8G
: "${OSWORLD_DIR:?Set OSWORLD_DIR}"
: "${OSCOMBO_GUEST_IMAGE:?Set OSCOMBO_GUEST_IMAGE}"
: "${OSCOMBO_RUNTIME_IMAGE:?Set OSCOMBO_RUNTIME_IMAGE}"
python="${OSWORLD_DIR%/}/.venv/bin/python"
[[ -x "$python" ]] || { echo 'OSWorld Python is not executable' >&2; exit 3; }
mode="${1:-}"
model=0
round=''
case "$mode" in
  control-positive-shared) side=shared; extra=();;
  control-positive-isolated) side=isolated; extra=();;
  control-negative-shared) side=shared; extra=(--scripted-negative);;
  control-negative-isolated) side=isolated; extra=(--scripted-negative);;
  control-probe-shared) side=shared; extra=(--scripted-view-version-probe);;
  control-probe-isolated) side=isolated; extra=(--scripted-view-version-probe);;
  pilot) side=isolated; model=1; extra=(--diagnostic-step-limit 12 --model-timeout 600);;
  isolated) side=isolated; model=1; extra=(--model-timeout 1200);;
  shared) side=shared; model=1; extra=(--model-timeout 1200);;
  shared_lock) side=shared; model=1; extra=(--model-timeout 1200 --gui-input-lock);;
  *) echo 'Expected control-positive/negative/probe-shared/isolated, pilot, isolated, shared or shared_lock' >&2; exit 2;;
esac
case "$mode" in
  pilot) fixture_seed='codesk-wa-v2-pilot-20261031' ;;
  isolated|shared|shared_lock)
    round="${2:-}"
    case "$round" in round1|round2|round3) ;; *) echo 'Formal arm requires round1, round2 or round3' >&2; exit 2;; esac
    fixture_seed="codesk-wa-v2-${round}-20261031" ;;
  *) fixture_seed='codesk-wa-v2-control-20261031' ;;
esac
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo 'Tracked source changes must be committed before a Guest run' >&2
    exit 3
fi
commit=$(git rev-parse --verify HEAD) || exit 3
export CODESK_CASE7_SOURCE_COMMIT="$commit"
if [[ "$mode" == isolated || "$mode" == shared || "$mode" == shared_lock ]]; then
    freeze="${CODESK_CASE7_V2_FREEZE_FILE:-}"
    if [[ ! -f "$freeze" ]]; then echo 'A verified v2 freeze record is required' >&2; exit 3; fi
    "$python" - "$freeze" "$commit" "$round" "$fixture_seed" "$OSCOMBO_GUEST_IMAGE" "$OSCOMBO_RUNTIME_IMAGE" <<'PY' || exit 3
import json,sys,tempfile
from pathlib import Path
from oscombo.collab.workspace_assembly_lite_v2 import fixtures
from oscombo.collab.workspace_assembly_lite_v2.freeze import SEQUENCE
x=json.load(open(sys.argv[1],encoding='utf-8'))
expected={'source_commit':sys.argv[2], 'case_id':'CDD-WA-LITE-002', 'case_version':'2.0.0',
          'model':'gpt-6-astra', 'steps_per_role':25, 'active_seconds_per_role':1200,
          'guest_cpus':8, 'guest_ram':'8G', 'controls_verified':True, 'pilot_reviewed':True}
if any(x.get(k)!=v for k,v in expected.items()):
    raise SystemExit('freeze record does not match the source/configuration gates')
if x.get('round_seeds',{}).get(sys.argv[3]) != sys.argv[4]:
    raise SystemExit('formal fixture seed differs from the frozen round')
if x.get('formal_sequence') != [list(pair) for pair in SEQUENCE]:
    raise SystemExit('formal sequence differs from the preregistration')
image=Path(sys.argv[5]).resolve(strict=True)
stat=image.stat()
if x.get('image_path') != str(image) or x.get('image_stat') != {'bytes':stat.st_size, 'mtime_ns':stat.st_mtime_ns}:
    raise SystemExit('Guest base image changed since freeze')
if x.get('runtime_image') != sys.argv[6]:
    raise SystemExit('Guest runtime image differs from freeze')
with tempfile.TemporaryDirectory(prefix='codesk-wa-v2-guard-') as temp:
    manifest=fixtures.build_fixture(Path(temp)/'fixture', seed=sys.argv[4])
if x.get('round_fixture_sha256',{}).get(sys.argv[3]) != manifest['fixture_sha256']:
    raise SystemExit('round fixture differs from freeze')
PY
fi
stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
run_id="${CODESK_CASE7_V2_RUN_ID:-wa-lite-v2-${mode}${round:+-$round}-${stamp}}"
if [[ ! "$run_id" =~ ^wa-lite-v2-[a-zA-Z0-9_.-]+$ || -e "$PWD/runs/$run_id" ]]; then
    echo 'Unsafe or already-used run ID' >&2; exit 3
fi
if [[ "$mode" == isolated || "$mode" == shared || "$mode" == shared_lock ]]; then
    campaign_state="${CODESK_CASE7_V2_CAMPAIGN_STATE:-}"
    if [[ ! -f "$campaign_state" ]]; then echo 'Formal run requires a campaign reservation' >&2; exit 3; fi
    "$python" - "$campaign_state" "$freeze" "$run_id" "$round" "$mode" <<'PY' || exit 3
import sys
from pathlib import Path
from oscombo.collab.workspace_assembly_lite_v2.campaign import verify_reservation
verify_reservation(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5])
PY
fi
run_root="$PWD/runs/$run_id"
log="$PWD/audits/three_lite_cases_20261029/${run_id}-driver.log"
preflight="$PWD/audits/three_lite_cases_20261029/${run_id}-preflight.txt"
free_kib=$(df -Pk "$PWD" | awk 'NR==2 {print $4}') || exit 3
if [[ ! "$free_kib" =~ ^[0-9]+$ ]] || (( free_kib < 15 * 1024 * 1024 )); then
    printf 'NOT_STARTED_LOW_DISK %s\n' "$free_kib" > "$preflight"; exit 3
fi
if ! guests=$(docker ps --filter label=oscombo=1 --format '{{.ID}}' 2>/dev/null); then
    printf 'NOT_STARTED_DOCKER_UNAVAILABLE\n' > "$preflight"; exit 3
fi
if [[ -n "$guests" ]]; then printf 'NOT_STARTED_ACTIVE_GUEST\n' > "$preflight"; exit 3; fi
if ! "$python" -m oscombo.collab.workspace_assembly_lite_v2.preflight > "$preflight"; then
    echo 'NOT_STARTED_INOTIFY_HEADROOM' >> "$preflight"; exit 3
fi
printf 'source_commit=%s\nfixture_seed=%s\nfree_kib=%s\nguest_cpus=8\nguest_ram=8G\n' "$commit" "$fixture_seed" "$free_kib" >> "$preflight"
model_args=()
credential_value=''
if (( model )); then
    credential_file="${CODESK_HAOGPT_KEY_FILE:-../.codesk-secrets/haogpt_20261027.key}"
    if [[ ! -f "$credential_file" || "$(stat -c %a "$credential_file")" != 600 ||
          "$(stat -c %u "$credential_file")" != "$(id -u)" ]]; then
        echo 'Model credential file is missing or not owner-only' >&2; exit 3
    fi
    IFS= read -r credential_value < "$credential_file"
    [[ -n "$credential_value" ]] || { echo 'Model credential is empty' >&2; exit 3; }
    model_args=(--model gpt-6-astra --base-url https://api.haogpt.net/v1
        --api-key-env AIGCBEST_API_KEY --mcp-python "$python" --yield-wait-lifecycle --actor-mcp-only)
fi
unset AIGCBEST_API_KEY CODESK_HAOGPT_KEY_FILE
AIGCBEST_API_KEY="$credential_value" "$python" -m oscombo.collab.workspace_assembly_lite_v2.live_pilot \
    --condition "collaborative_${side}" --run-root "$run_root" --provider "$OSWORLD_DIR" \
    --image "$OSCOMBO_GUEST_IMAGE" --runtime "$OSCOMBO_RUNTIME_IMAGE" --fixture-seed "$fixture_seed" \
    "${model_args[@]}" "${extra[@]}" > "$log" 2>&1 &
driver_pid=$!
unset credential_value
for _ in {1..100}; do
    [[ -d "$run_root" ]] && break
    kill -0 "$driver_pid" 2>/dev/null || break
    sleep 0.1
done
sampler_pid=''
if [[ -d "$run_root" ]] && kill -0 "$driver_pid" 2>/dev/null; then
    "$python" -m oscombo.collab.workspace_assembly_lite_v2.resource_sampler "$run_root" \
        > "${log%.log}-sampler.log" 2>&1 &
    sampler_pid=$!
fi
wait "$driver_pid"
exit_code=$?
if [[ -n "$sampler_pid" ]]; then kill "$sampler_pid" 2>/dev/null || true; wait "$sampler_pid" 2>/dev/null || true; fi
if [[ -f "$run_root/bridge_cleanup_pending.json" ]]; then
    # wait above proves the coordinator (and its daemon writer) exited.
    # This helper acquires the old lease and removes only exact labelled IDs.
    if ! "$python" -m oscombo.collab.workspace_assembly_lite_v2.deferred_cleanup "$run_root" \
        > "${log%.log}-deferred-cleanup.log" 2>&1; then
        echo 'Deferred Guest cleanup failed; retain run-owned resources for review' >&2
    fi
    exit_code=3
fi
mark_resource_invalid() {
    if [[ -f "$run_root/result.json" ]]; then
        "$python" - "$run_root/result.json" "${1:-QEMU configuration or resource samples not verified}" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]); result=json.loads(p.read_text())
result['pre_resource_status']=result.get('status')
result['status']='INVALID_INFRA_OR_RUNNER_ERROR'
result['infrastructure_audit_error']=sys.argv[2]
tmp=p.with_suffix('.json.tmp'); tmp.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n'); tmp.replace(p)
PY
    fi
}
if [[ -f "$run_root/provenance.json" ]] && [[ -f "$run_root/result.json" || -f "$run_root/failure.json" ]]; then
    if ! "$python" -m oscombo.collab.workspace_assembly_lite_v2.resource_sampler "$run_root" --summarize \
        > "${log%.log}-resource-audit.log" 2>&1; then
        mark_resource_invalid
        echo 'Resource audit could not be completed; preserve this attempt as infrastructure review' >&2
        exit 3
    fi
    if ! "$python" - "$run_root/resource_audit.json" <<'PY'
import json,sys
if not json.load(open(sys.argv[1],encoding='utf-8')).get('valid'):
    raise SystemExit(3)
PY
    then
        mark_resource_invalid
        echo 'QEMU configuration or resource samples not verified; preserve as infrastructure review' >&2
        exit 3
    fi
else
    echo 'Run lacks terminal provenance or result; preserve as infrastructure review' >&2
    exit 3
fi
if (( model )) && [[ "$exit_code" == 0 || "$exit_code" == 2 ]]; then
    if ! "$python" -m oscombo.collab.workspace_assembly_lite_v2.contract "$run_root" \
        > "${log%.log}-contract-audit.log" 2>&1; then
        mark_resource_invalid 'model transport or Actor tool contract could not be verified'
        echo 'Model transport/tool boundary invalid; preserve this attempt as infrastructure review' >&2
        exit 3
    fi
    if ! "$python" -m oscombo.collab.workspace_assembly_lite_v2.analyze "$run_root" \
        > "${log%.log}-metrics.log" 2>&1; then
        mark_resource_invalid 'model timing/usage/lock metrics could not be reconstructed'
        echo 'Model metrics unavailable; preserve this attempt as infrastructure review' >&2
        exit 3
    fi
    if ! "$python" - "$run_root/model_metrics_v2.json" "$mode" <<'PY'
import json,sys
data=json.load(open(sys.argv[1],encoding='utf-8')); mode=sys.argv[2]
if data.get('lifecycle_errors'):
    raise SystemExit('lifecycle timing records are inconsistent')
for role in 'AB':
    actor=data['actors'][role]
    if mode=='shared_lock' and actor['locked_inputs'] != actor['executed_inputs']:
        raise SystemExit('shared lock did not cover every executed input')
    if mode!='shared_lock' and actor['locked_inputs']:
        raise SystemExit('unexpected GUI input lock outside lock arm')
PY
    then
        mark_resource_invalid 'model lifecycle or input-lock evidence is inconsistent'
        echo 'Lifecycle/lock evidence invalid; preserve as infrastructure review' >&2
        exit 3
    fi
fi
printf 'run_id=%s\nexit=%s\n' "$run_id" "$exit_code"
exit "$exit_code"
