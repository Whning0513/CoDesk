import json

from audits.three_lite_cases_20261029.audit_case7_handoff import audit


def _write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def test_audit_distinguishes_message_only_from_delivered_gui_read(tmp_path):
    (tmp_path / "provenance.json").write_text(json.dumps({
        "condition": "collaborative_isolated", "case_version": "1.0.2",
        "gui_input_lock": False}))
    (tmp_path / "oracle.json").write_text(json.dumps({"joint_success": True}))
    _write_rows(tmp_path / "workspace_versions/events.jsonl", [
        {"event": "revision_saved", "actor": "A", "revision": 1, "time": 12},
        {"event": "transfer_verified", "actor": "A", "revision": 1, "time": 14},
        {"event": "revision_saved", "actor": "B", "revision": 1, "time": 20}])
    _write_rows(tmp_path / "collaboration/events.jsonl", [
        {"type": "message", "actor": "A", "recipient": "B", "timestamp": 13}])
    _write_rows(tmp_path / "actor_runs/A/A/actions.jsonl", [
        {"n": 1, "executed": True, "action_started_at": 11,
         "window_before": "inspection_note.txt (/tmp/case/outputs/agent_A) - gedit"}])
    b_path = tmp_path / "actor_runs/B/B/actions.jsonl"
    _write_rows(b_path, [{"n": 1, "executed": True, "action_started_at": 15,
                          "window_before": "handoff_report.odt - LibreOffice Writer"}])
    message_only = audit(tmp_path)
    assert message_only["oracle_joint_success"]
    assert not message_only["behavioral_handoff_verified"]
    _write_rows(b_path, [{"n": 1, "executed": True, "action_started_at": 15,
                          "window_before": "inspection_note.txt (/tmp/case/outputs/agent_A) - gedit"}])
    gui_read = audit(tmp_path)
    assert gui_read["behavioral_handoff_verified"]
    assert gui_read["v1p2_full_process_verified"]


def test_audit_flags_gui_path_open_for_manual_review_without_claiming_handoff(tmp_path):
    (tmp_path / "provenance.json").write_text(json.dumps({
        "condition": "collaborative_isolated", "case_version": "1.0.2"}))
    (tmp_path / "oracle.json").write_text(json.dumps({"joint_success": True}))
    _write_rows(tmp_path / "workspace_versions/events.jsonl", [
        {"event": "revision_saved", "actor": "A", "revision": 1, "time": 12},
        {"event": "transfer_verified", "actor": "A", "revision": 1, "time": 14},
        {"event": "revision_saved", "actor": "B", "revision": 1, "time": 30}])
    _write_rows(tmp_path / "collaboration/events.jsonl", [
        {"type": "message", "actor": "A", "recipient": "B", "timestamp": 15}])
    _write_rows(tmp_path / "actor_runs/B/B/actions.jsonl", [
        {"n": 5, "tool": "type_text", "args": {"text": "/tmp/case/outputs/agent_A/inspection_note.txt"},
         "window_before": "Open", "action_started_at": 18},
        {"n": 6, "tool": "key", "args": {"keys": "Return"},
         "window_before": "Open", "action_started_at": 19},
        {"n": 7, "tool": "click", "args": {"x": 100, "y": 100},
         "window_before": "inspection_note.txt (read-only) - LibreOffice Writer",
         "action_started_at": 21}])
    shot = tmp_path / "actor_runs/B/B/shots/007.png"
    shot.parent.mkdir(parents=True)
    shot.write_bytes(b"screenshot to review")
    candidate = audit(tmp_path)
    assert candidate["manual_review_required"]
    assert candidate["B_GUI_path_open_candidates"][0]["screenshot"] == "actor_runs/B/B/shots/007.png"
    assert not candidate["behavioral_handoff_verified"]
    assert not candidate["v1p2_full_process_verified"]
