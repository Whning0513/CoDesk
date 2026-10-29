import json

from PIL import Image, ImageDraw

from oscombo.collab.lite_file_guest_pilot import _browser_trace_audit


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
