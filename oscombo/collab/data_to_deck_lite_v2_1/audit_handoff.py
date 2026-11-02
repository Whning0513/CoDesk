"""Topology-aware saved handoff audit; does not claim B opened an ODS GUI."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from audits.lite_v2_20261027.audit_handoff import audit as baseline_audit


def audit(root: Path) -> dict:
    baseline = baseline_audit(root)
    result = json.loads((root / 'result.json').read_text())
    events = [json.loads(line) for line in (root / 'workspace_versions/events.jsonl').read_text().splitlines()]
    messages = [json.loads(line) for line in (root / 'collaboration/events.jsonl').read_text().splitlines()]
    source = baseline.get('a_revision') or {}
    msg = baseline.get('a_message') or {}
    committed = [e for e in events if e.get('event') == 'revision_committed' and e.get('actor') == 'A'
                 and e.get('revision') == source.get('revision') and e.get('sha256') == source.get('sha256')
                 and e.get('time', float('inf')) < msg.get('timestamp', 0)]
    revision = source.get('revision')
    path = root / 'workspace_versions/A' / f"revision-{revision if type(revision) is int else -1:06d}.ods"
    archived_matches = path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == source.get('sha256')
    messages_a = [m for m in messages if m.get('actor') == 'A' and m.get('message_id') == msg.get('message_id')]
    a_message = messages_a[0] if messages_a else {}
    # For Shared a verified commit is the same desktop file; no inter-Guest
    # transfer event exists. Isolated retains the original transfer check.
    shared_delivery = (result.get('condition') == 'collaborative_shared' and bool(committed)
                       and archived_matches and bool(source.get('revision', 0)))
    delivery = baseline.get('source_delivered') or shared_delivery
    success = bool(delivery and msg and baseline.get('b_read_message_stdout_item_index') is not None
                   and baseline.get('b_first_gui_edit_after_read_item_index') is not None
                   and (baseline.get('b_revision') or {}).get('time', 0) > msg.get('timestamp', 0)
                   and baseline.get('artifact_joint_success'))
    amount = (result.get('oracle') or {}).get('expected_change_evaluator_only')
    normalized_body = str(a_message.get('body') or '').replace('−', '-')
    return {'run_id': root.name, 'baseline_audit_preserved': baseline,
            'same_desktop_committed_revision_verified': bool(shared_delivery),
            'a_message_contains_result_and_source': bool(type(amount) in (int, float) and
                str(int(amount)) in normalized_body and 'B3:E4' in normalized_body),
            'attachment_count': len(a_message.get('attachment_ids') or []),
            'message_read_then_gui_edit_then_saved': success,
            'scope': 'A saved revision plus B read of message and subsequent GUI edit; not evidence B opened the ODS in GUI.'}


if __name__ == '__main__':
    print(json.dumps(audit(Path(sys.argv[1]).resolve()), indent=2))
