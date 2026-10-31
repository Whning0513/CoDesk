"""Check that task failures are retained and environment faults stop the triad."""

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = (Path(__file__).resolve().parents[1] / 'audits' / 'three_lite_cases_20261029'
          / 'case5_audit_completed_arm.py')
module_spec = importlib.util.spec_from_file_location('case5_completed_arm_audit', SCRIPT)
module = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(module)


@pytest.mark.parametrize('fault', [None, 'reopen', 'sync', 'relay', 'boundary', 'resources',
                                   'host', 'topology', 'system_collision',
                                   'missing_system_shot', 'missing_actor_shot'])
def test_audit_retains_model_failure_and_stops_on_evidence_fault(tmp_path, fault):
    root = tmp_path / 'case5-example'
    root.mkdir()
    run_id = root.name
    result = {'run_id': run_id, 'condition': 'collaborative_isolated', 'status': 'FAIL',
              'model': 'gpt-6-astra', 'postscore_lifecycle_ok': True,
              'actor_results': {'A': {'model': 'gpt-6-astra', 'guest_key': 'A'},
                                'B': {'model': 'gpt-6-astra', 'guest_key': 'B'}},
              'reopen': [{'role': 'A', 'same_bytes': True}, {'role': 'B', 'missing_output': True}],
              'reset': [{'old': 'a0', 'new': 'a1', 'workspace_clean': True,
                         'labels': {'oscombo': '1', 'oscombo.run': run_id}},
                        {'old': 'b0', 'new': 'b1', 'workspace_clean': True,
                         'labels': {'oscombo': '1', 'oscombo.run': run_id}}]}
    sync = {'verified': True, 'transient_errors': []}
    relay = {'actor': 'A', 'actor_mcp_only': True, 'upstream_status': 200, 'model': 'gpt-6-astra'}
    boundary = {'actors': {role: {'total_tool_calls': 1, 'outside_gui_collaboration_contract': {}}
                           for role in ('A', 'B')}}
    resources = {'samples': 3, 'guest_count_peak': 2}
    result['oracle'] = {'joint_success': False}
    if fault == 'reopen':
        result['reopen'][0]['same_bytes'] = False
    if fault == 'sync':
        sync['transient_errors'] = ['bridge connection lost']
    if fault == 'relay':
        relay['upstream_status'] = 500
    if fault == 'boundary':
        boundary['actors']['B']['outside_gui_collaboration_contract'] = {'shell': 1}
    if fault == 'resources':
        resources['guest_count_peak'] = 1
    if fault == 'topology':
        result['actor_results']['B']['guest_key'] = 'A'
    for filename, value in [('result.json', result), ('provenance.json', {'actor_mcp_only': True}),
                            ('workspace_sync_result.json', sync), ('missing_outputs.json', ['B']),
                            ('model_metrics.json', {'actors': {'A': {}}}), ('oracle.json', result['oracle'])]:
        (root / filename).write_text(json.dumps(value))
    (root / 'codex_relay_events.jsonl').write_text(json.dumps(relay) + '\n'
                                                    + json.dumps({**relay, 'actor': 'B'}) + '\n')
    if fault != 'host':
        (root / 'host_resources.jsonl').write_text(json.dumps({'time': 1, 'disk_free_bytes': 1,
                                                               'meminfo': {}, 'io_pressure': ''}) + '\n')
    (root / 'actual_guest.png').write_bytes(b'screenshot marker')
    (root / 'other_guest.png').write_bytes(b'other screenshot marker')
    paths = ['actual_guest.png', 'actual_guest.png' if fault == 'system_collision' else
             'missing.png' if fault == 'missing_system_shot' else 'other_guest.png']
    (root / 'gui_actions.jsonl').write_text(''.join(json.dumps({'screenshot': path}) + '\n' for path in paths))
    for role in ('A', 'B'):
        actor_root = root / 'actor_runs' / role / role
        (actor_root / 'shots').mkdir(parents=True)
        (actor_root / 'actions.jsonl').write_text(json.dumps({'n': 1, 'tool': 'screenshot'}) + '\n')
        if not (fault == 'missing_actor_shot' and role == 'B'):
            (actor_root / 'shots' / '001.png').write_bytes(b'actor screenshot marker')
    boundary_path, resource_path = tmp_path / 'boundary.json', tmp_path / 'resources.json'
    boundary_path.write_text(json.dumps(boundary))
    resource_path.write_text(json.dumps(resources))
    outcome = module.audit(root, 2, 'collaborative_isolated', boundary_path, resource_path)
    assert outcome['valid_to_continue'] is (fault is None)
    assert bool(outcome['errors']) is (fault is not None)
