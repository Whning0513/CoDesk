"""Fail-closed Case 1 artifact, bridge history and reset audit; no Actor secrets."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from . import fixtures, oracle, spec


def audit(root: Path) -> dict:
    errors = []
    try:
        result = json.loads((root / 'result.json').read_text())
        sync = json.loads((root / 'workspace_sync_result.json').read_text())
        stored = json.loads((root / 'oracle.json').read_text())
        provenance = json.loads((root / 'provenance.json').read_text())
        events = [json.loads(line) for line in (root / 'workspace_versions/events.jsonl').read_text().splitlines()]
        outputs = {role: root / 'artifacts' / role / Path(spec.OUTPUTS[role]).name for role in 'AB'}
        evaluated = oracle.evaluate(root / 'fixtures' / spec.FIXTURE_NAMES['authority'], outputs['A'],
                                    root / 'fixtures' / spec.FIXTURE_NAMES['draft'], outputs['B'])
        if stored != evaluated or result.get('oracle') != stored:
            errors.append('independent Oracle differs from stored result')
        if result.get('run_id') != root.name or provenance.get('run_id') != root.name:
            errors.append('run identity mismatch')
        if provenance.get('case_id') != spec.CASE_ID or provenance.get('case_version') != spec.CASE_VERSION:
            errors.append('case identity mismatch')
        if result.get('status') not in {'PASS', 'FAIL'} or (result['status'] == 'PASS') != bool(stored.get('joint_success')):
            errors.append('task status does not match independent Oracle')
        fault_events = {'guest_probe_error', 'guest_read_error', 'transfer_error', 'peer_view_error',
                        'peer_view_conflict', 'ownership_or_sync_conflict', 'sync_error'}
        if not events or any(not isinstance(e, dict) or e.get('run_id') != root.name for e in events):
            errors.append('bridge history missing or wrong run')
        if any(e.get('event') in fault_events for e in events) or sync.get('transient_errors'):
            errors.append('bridge history has a transport or sync fault')
        if sync.get('verified') is not True:
            errors.append('final bridge sync unverified')
        items = result.get('artifact_manifest', {}).get('artifacts', [])
        for role in 'AB':
            candidate = next((x for x in items if x.get('actor') == role), None)
            if not candidate or not outputs[role].is_file() or hashlib.sha256(outputs[role].read_bytes()).hexdigest() != candidate.get('sha256'):
                errors.append(f'{role} output missing or hash differs')
        if result.get('reopen_complete') is not True:
            errors.append('GUI reopen incomplete')
        reopens = json.loads((root / 'reopen_evidence.json').read_text())
        for role in 'AB':
            if not any(x.get('actor') == role and x.get('same_bytes_after_gui_reopen') is True for x in reopens):
                errors.append(f'{role} byte-equal GUI reopen missing')
            if result.get('condition') == 'collaborative_isolated' and not any(
                    x.get('actor') == role and x.get('peer_gui_opened_readonly') is True for x in reopens):
                errors.append(f'{role} peer Guest readonly GUI reopen missing')
        expected = 2 if result.get('condition') == 'collaborative_isolated' else 1
        resets = result.get('reset') or []
        if len(resets) != expected or any(x.get('workspace_clean') is not True for x in resets):
            errors.append('run-owned Guest reset incomplete')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(f'missing or malformed evidence: {type(exc).__name__}')
    return {'run_id': root.name, 'valid': not errors, 'errors': errors,
            'scope': 'artifact and bridge evidence; model transport checked separately'}


if __name__ == '__main__':
    result = audit(Path(sys.argv[1]))
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['valid'] else 3)
