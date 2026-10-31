"""Post-run gate: distinguish task outcomes from incomplete execution evidence."""

import argparse
from collections import Counter
import json
from pathlib import Path


def audit(root: Path, driver_exit: int, condition: str, boundary_path: Path,
          resource_path: Path) -> dict:
    errors, warnings = [], []

    def read_json(path):
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            errors.append(f'{path.name}: {type(exc).__name__}')
            return {}

    result = read_json(root / 'result.json')
    provenance = read_json(root / 'provenance.json')
    sync = read_json(root / 'workspace_sync_result.json')
    boundary = read_json(boundary_path)
    resources = read_json(resource_path)
    metrics = read_json(root / 'model_metrics.json')
    oracle = read_json(root / 'oracle.json')
    missing = read_json(root / 'missing_outputs.json')
    if not isinstance(missing, list):
        errors.append('missing_outputs is not a list')
        missing = []
    if result.get('run_id') != root.name or result.get('condition') != condition:
        errors.append('result run_id or condition mismatch')
    status = result.get('status')
    if (status, driver_exit) not in {('PASS', 0), ('FAIL', 2)}:
        errors.append(f'invalid status/exit combination: {status!r}/{driver_exit}')
    if result.get('oracle') != oracle or oracle.get('joint_success') is not (status == 'PASS'):
        errors.append('independent Oracle result is missing or inconsistent')
    if result.get('model') != 'gpt-6-astra' or provenance.get('actor_mcp_only') is not True:
        errors.append('model or request-level whitelist configuration mismatch')
    actors = result.get('actor_results') or {}
    if set(actors) != {'A', 'B'} or any(actors[r].get('model') != 'gpt-6-astra' for r in actors):
        errors.append('independent A/B model records missing or mismatched')
    elif ((actors['A'].get('guest_key') == actors['B'].get('guest_key'))
          != condition.endswith('shared')):
        errors.append('A/B Guest topology mismatch')
    if result.get('postscore_lifecycle_ok') is not True:
        errors.append('postscore lifecycle is not valid')
    reopen = result.get('reopen', [])
    if len(reopen) != 2 or {x.get('role') for x in reopen} != {'A', 'B'}:
        errors.append('A/B reopen records missing')
    for row in reopen:
        if row.get('missing_output') is True:
            if row.get('role') not in missing:
                errors.append('missing output is not recorded consistently')
        elif row.get('role') in missing:
            errors.append('reopen record contradicts missing output list')
        elif row.get('same_bytes') is not True or row.get('postscore_error') or row.get('gui_reopen') == 'skipped_unsaved_buffer':
            errors.append(f"{row.get('role')} saved output GUI reopen incomplete")
    expected_guests = 2 if condition.endswith('isolated') else 1
    resets = result.get('reset', [])
    if len(resets) != expected_guests:
        errors.append('wrong reset count')
    for row in resets:
        if (row.get('workspace_clean') is not True or not row.get('old') or not row.get('new')
                or row['old'] == row['new'] or row.get('labels', {}).get('oscombo') != '1'
                or row.get('labels', {}).get('oscombo.run') != root.name):
            errors.append('reset ownership or clean-workspace evidence invalid')
    if sync.get('verified') is not True:
        errors.append('workspace bridge not verified')
    if sync.get('transient_errors'):
        errors.append('workspace bridge errors require review')
    for role in ('A', 'B'):
        actor = boundary.get('actors', {}).get(role, {})
        if not actor.get('total_tool_calls') or actor.get('outside_gui_collaboration_contract') != {}:
            errors.append(f'{role} tool boundary missing or violated')
    if resources.get('samples', 0) < 1 or resources.get('guest_count_peak') != expected_guests:
        errors.append('QEMU resource evidence missing or incomplete')
    if not metrics.get('actors'):
        errors.append('model timing and token metrics missing')
    if not any(root.rglob('*.png')):
        errors.append('real Guest screenshots missing')
    try:
        host_rows = [json.loads(line) for line in (root / 'host_resources.jsonl').read_text().splitlines()]
        if not host_rows or not all('disk_free_bytes' in row and 'meminfo' in row and 'io_pressure' in row for row in host_rows):
            errors.append('host resource samples missing or invalid')
    except (OSError, ValueError):
        host_rows = []
        errors.append('host resource samples missing or invalid')
    try:
        relay = [json.loads(line) for line in (root / 'codex_relay_events.jsonl').read_text().splitlines()]
        if ({row.get('actor') for row in relay} != {'A', 'B'}
                or any(row.get('actor_mcp_only') is not True or row.get('model') != 'gpt-6-astra' for row in relay)):
            errors.append('relay whitelist evidence missing or invalid')
        statuses = Counter(str(row.get('upstream_status')) for row in relay)
        if any(row.get('upstream_status') != 200 for row in relay):
            errors.append('non-200 or interrupted relay response requires review')
    except (OSError, ValueError):
        statuses = Counter()
        errors.append('relay events missing or invalid')
    return {'run_id': root.name, 'condition': condition, 'driver_status': status,
            'driver_exit': driver_exit, 'valid_to_continue': not errors,
            'errors': errors, 'warnings': warnings, 'relay_status_counts': dict(statuses),
            'expected_guest_count': expected_guests, 'host_samples': len(host_rows)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run_root', type=Path)
    parser.add_argument('--exit-code', required=True, type=int)
    parser.add_argument('--condition', required=True)
    parser.add_argument('--boundary', required=True, type=Path)
    parser.add_argument('--resources', required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.run_root, args.exit_code, args.condition, args.boundary, args.resources)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['valid_to_continue'] else 3


if __name__ == '__main__':
    raise SystemExit(main())
