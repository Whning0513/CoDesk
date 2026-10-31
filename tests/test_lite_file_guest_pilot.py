import json

from PIL import Image, ImageDraw
import pytest

from oscombo.collab.lite_file_guest_pilot import (
    _await_delivered_revision, _browser_trace_audit, _postscore_lifecycle_ok,
    _result_exit_code,
)


def test_result_exit_codes_distinguish_task_failure_from_invalid_run():
    assert _result_exit_code("PASS") == 0
    assert _result_exit_code("FAIL") == 2
    assert _result_exit_code("INVALID_INFRA_OR_RUNNER_ERROR") == 3
    assert _result_exit_code("unexpected_status") == 3


def test_scripted_handoff_waits_for_delivered_new_revision(monkeypatch):
    class Bridge:
        def __init__(self, revisions):
            self.revisions = iter(revisions)

        def snapshot(self):
            return {"A": next(self.revisions)}

    monkeypatch.setattr("oscombo.collab.lite_file_guest_pilot.time.sleep", lambda _: None)
    ready = {"revision": 1, "delivered": True, "sha256": "new"}
    bridge = Bridge([{"revision": 0, "delivered": True},
                     {"revision": 1, "delivered": False}, ready])
    assert _await_delivered_revision(bridge, "A", timeout_seconds=5) == ready
    with pytest.raises(RuntimeError, match="new revision"):
        _await_delivered_revision(Bridge([{"revision": 0, "delivered": True}]),
                                  "A", timeout_seconds=0)


def test_postscore_lifecycle_separates_missing_task_output_from_reopen_fault():
    assert _postscore_lifecycle_ok([
        {"role": "A", "missing_output": True, "same_bytes": False},
        {"role": "B", "same_bytes": True}])
    assert not _postscore_lifecycle_ok([
        {"role": "A", "same_bytes": False, "postscore_error": "modal"},
        {"role": "B", "same_bytes": True}])


def test_browser_trace_requires_visible_single_row_after_saved_revision(tmp_path):
    versions = tmp_path / "workspace_versions"
    versions.mkdir()
    (versions / "events.jsonl").write_text(json.dumps({
        "event": "revision_saved", "actor": "A", "revision": 1, "time": 10.0}) + "\n")
    screenshots = tmp_path / "screenshots"
    screenshots.mkdir()
    image = Image.new("RGB", (1920, 1080), "white")
    draw = ImageDraw.Draw(image)
    for y in (354, 398, 442, 486, 530):
        draw.line((545, y, 1445, y), fill="black")
    image.save(screenshots / "before.png")
    draw.rectangle((545, 443, 1445, 531), fill="white")
    image.save(screenshots / "after.png")
    events = [
        {"actor": "B", "action_id": "B-001", "ended_at": 20.0,
         "window_after": {"output": "ACTIVE_WINDOW_TITLE=OrderDesk Lite - Google Chrome"},
         "screenshot": "screenshots/before.png"},
    ]
    path = tmp_path / "gui_actions.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in events) + "\n")
    assert not _browser_trace_audit(tmp_path)["browser_one_visible_row_after_handoff"]
    events.append({**events[0], "action_id": "B-002", "ended_at": 21.0,
                   "screenshot": "screenshots/after.png"})
    path.write_text("\n".join(json.dumps(x) for x in events) + "\n")
    assert _browser_trace_audit(tmp_path)["browser_one_visible_row_after_handoff"]
