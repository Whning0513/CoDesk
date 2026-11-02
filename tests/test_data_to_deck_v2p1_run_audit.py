import hashlib
import json

from oscombo.collab.data_to_deck_lite_v2_1 import audit_run, spec


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def _run(tmp_path, monkeypatch):
    root = tmp_path / 'case1-test'; root.mkdir()
    score = {'joint_success': True}
    monkeypatch.setattr(audit_run.oracle, 'evaluate', lambda *args: score)
    items = []
    for role in 'AB':
        path = root / 'artifacts' / role / spec.OUTPUTS[role].split('/')[-1]
        path.parent.mkdir(parents=True); path.write_bytes(role.encode())
        items.append({'actor': role, 'sha256': hashlib.sha256(role.encode()).hexdigest()})
    result = {'run_id': root.name, 'status': 'PASS', 'oracle': score,
              'condition': 'collaborative_shared', 'artifact_manifest': {'artifacts': items},
              'reopen_complete': True, 'reset': [{'workspace_clean': True}]}
    _write(root / 'result.json', result)
    _write(root / 'oracle.json', score)
    _write(root / 'provenance.json', {'run_id': root.name, 'case_id': spec.CASE_ID, 'case_version': spec.CASE_VERSION})
    _write(root / 'workspace_sync_result.json', {'verified': True, 'transient_errors': []})
    _write(root / 'reopen_evidence.json', [{'actor': role, 'same_bytes_after_gui_reopen': True} for role in 'AB'])
    events = root / 'workspace_versions/events.jsonl'; events.parent.mkdir()
    events.write_text(json.dumps({'run_id': root.name, 'event': 'revision_committed'}) + '\n')
    return root


def test_audit_rejects_bridge_fault_even_after_final_sync(tmp_path, monkeypatch):
    root = _run(tmp_path, monkeypatch)
    assert audit_run.audit(root)['valid'] is True
    with (root / 'workspace_versions/events.jsonl').open('a') as stream:
        stream.write(json.dumps({'run_id': root.name, 'event': 'guest_probe_error'}) + '\n')
    assert audit_run.audit(root)['valid'] is False


def test_audit_rejects_changed_saved_output(tmp_path, monkeypatch):
    root = _run(tmp_path, monkeypatch)
    path = root / 'artifacts/A' / spec.OUTPUTS['A'].split('/')[-1]
    path.write_bytes(b'modified')
    assert audit_run.audit(root)['valid'] is False
