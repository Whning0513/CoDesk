import json
import io

from PIL import Image, ImageDraw
import pytest

from oscombo.collab.lite_file_guest_pilot import (
    _browser_trace_audit, _dismiss_postscore_open_dialog,
    _postscore_lifecycle_ok, _result_exit_code,
)


def test_result_exit_codes_distinguish_task_failure_from_invalid_run():
    assert _result_exit_code("PASS") == 0
    assert _result_exit_code("FAIL") == 2
    assert _result_exit_code("INVALID_INFRA_OR_RUNNER_ERROR") == 3
    assert _result_exit_code("unexpected_status") == 3


def test_postscore_lifecycle_separates_missing_task_output_from_reopen_fault():
    assert _postscore_lifecycle_ok([
        {"role": "A", "missing_output": True, "same_bytes": False},
        {"role": "B", "same_bytes": True}])


def _png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (1920, 1080), "white").save(out, format="PNG")
    return out.getvalue()


class _PickerGuest:
    def __init__(self, root, titles, screenshot=None):
        self.root, self.guest_key = root, "B"
        (root / "screenshots").mkdir()
        self.titles = list(titles)
        self.title = self.titles.pop(0)
        self.frame = screenshot if screenshot is not None else _png()
        self.actions = []
        self.actor = None

    def active_window(self):
        return self.title

    def screenshot(self, patience):
        assert patience == 45
        return self.frame

    def run_pyautogui(self, code):
        assert self.actor == "system"
        self.actions.append(code)
        self.title = self.titles.pop(0)


def test_postscore_open_picker_is_cancelled_without_opening_entered_path(tmp_path):
    guest = _PickerGuest(tmp_path, ["Open", "Open", "handoff_report.odt - LibreOffice Writer"])
    assert _dismiss_postscore_open_dialog(guest, "reopen-B") is True
    assert len(guest.actions) == 2
    assert all("press('esc')" in code and "write(" not in code for code in guest.actions)
    assert (tmp_path / "screenshots/reopen-B-open-dialog-before.png").exists()
    assert (tmp_path / "screenshots/reopen-B-open-dialog-after.png").exists()
    row = json.loads((tmp_path / "observations.jsonl").read_text())
    assert row["escape_attempts"] == 2 and row["postscore_open_dialog_cancelled"] is True


def test_postscore_open_picker_noop_without_modal(tmp_path):
    guest = _PickerGuest(tmp_path, ["handoff_report.odt - LibreOffice Writer"])
    assert _dismiss_postscore_open_dialog(guest, "reopen-B") is False
    assert not guest.actions and not (tmp_path / "observations.jsonl").exists()


def test_postscore_open_picker_fails_closed_if_still_open(tmp_path):
    guest = _PickerGuest(tmp_path, ["Open", "Open", "Open", "Open"])
    with pytest.raises(RuntimeError, match="did not close"):
        _dismiss_postscore_open_dialog(guest, "reopen-B")
    assert len(guest.actions) == 3
    assert (tmp_path / "screenshots/reopen-B-open-dialog-before.png").exists()


def test_postscore_open_picker_rejects_unverifiable_frame_before_input(tmp_path):
    guest = _PickerGuest(tmp_path, ["Open"], screenshot=b"not a PNG")
    with pytest.raises(RuntimeError, match="cannot verify"):
        _dismiss_postscore_open_dialog(guest, "reopen-B")
    assert not guest.actions
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
