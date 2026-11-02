import hashlib
import json
from oscombo.collab.data_to_deck_lite_v2_1 import audit_handoff


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def test_shared_requires_committed_matching_revision_before_message(tmp_path, monkeypatch):
    root = tmp_path / 'run'; root.mkdir()
    archive = root / 'workspace_versions/A/revision-000001.ods'
    archive.parent.mkdir(parents=True); archive.write_bytes(b'saved')
    sha = hashlib.sha256(b'saved').hexdigest()
    baseline = {'a_revision': {'revision': 1, 'sha256': sha}, 'a_message': {'message_id': 'm1', 'timestamp': 5},
                'source_delivered': False, 'b_read_message_stdout_item_index': 2,
                'b_first_gui_edit_after_read_item_index': 3, 'b_revision': {'time': 6}, 'artifact_joint_success': True}
    monkeypatch.setattr(audit_handoff, 'baseline_audit', lambda root: baseline)
    _write(root / 'result.json', {'condition': 'collaborative_shared', 'oracle': {'expected_change_evaluator_only': -11}})
    (root / 'workspace_versions/events.jsonl').write_text(json.dumps({'event': 'revision_committed', 'actor': 'A', 'revision': 1, 'sha256': sha, 'time': 4}) + '\n')
    (root / 'collaboration').mkdir()
    (root / 'collaboration/events.jsonl').write_text(json.dumps({'actor': 'A', 'message_id': 'm1', 'body': '-11 B3:E4', 'attachment_ids': []}) + '\n')
    assert audit_handoff.audit(root)['message_read_then_gui_edit_then_saved'] is True
    archive.write_bytes(b'changed')
    assert audit_handoff.audit(root)['message_read_then_gui_edit_then_saved'] is False
