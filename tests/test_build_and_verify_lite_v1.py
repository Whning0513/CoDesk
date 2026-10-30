import json
import pytest

from PIL import Image, ImageDraw

from oscombo.collab.build_and_verify_lite_v1.fixtures import build_fixture
from oscombo.collab.build_and_verify_lite_v1.oracle import evaluate
from oscombo.collab.lite_file_guest_pilot import _browser_trace_audit, _editor_has_unsaved_buffer, run


def test_positive_and_negative_artifacts(tmp_path):
    fixture = tmp_path / "fixture"
    build_fixture(fixture)
    source = fixture / "orderdesk.html"
    qa = fixture / "qa_note.txt"
    a = tmp_path / "saved.html"
    b = tmp_path / "note.txt"
    a.write_text(source.read_text().replace('value="delievered"', 'value="delivered"'))
    b.write_text("Query: North\nStatus: Delivered\nVisible order IDs: OD-104\nSaved source: orderdesk.html\n")
    assert evaluate(source, a, qa, b)["joint_success"]
    a.write_text("\n".join("      " + line for line in a.read_text().splitlines()) + "\n")
    assert evaluate(source, a, qa, b)["joint_success"]
    a.write_text(source.read_text())
    assert not evaluate(source, a, qa, b)["joint_success"]
    a.write_text(source.read_text().replace('value="delievered"', 'value="delivered"'))
    b.write_text("Query: North\nStatus: Delivered\nVisible order IDs: OD-105\nSaved source: orderdesk.html\n")
    assert not evaluate(source, a, qa, b)["actors"]["B"]["success"]


def test_model_browser_screenshot_is_included_in_trace_audit(tmp_path):
    events = tmp_path / "workspace_versions/events.jsonl"
    events.parent.mkdir()
    events.write_text(json.dumps({"event": "revision_saved", "actor": "A",
                                  "revision": 1, "time": 100.0}) + "\n")
    action_path = tmp_path / "actor_runs/B/B/actions.jsonl"
    action_path.parent.mkdir(parents=True)
    action_path.write_text(json.dumps({"n": 21, "tool": "click", "executed": True,
                                       "screenshot_ended_at": 110.0,
                                       "window_after": "OrderDesk Lite - Google Chrome"}) + "\n")
    shot = action_path.parent / "shots/021.png"
    shot.parent.mkdir()
    image = Image.new("RGB", (1280, 720), "white")
    draw = ImageDraw.Draw(image)
    for y in (236, 265, 294):
        draw.line((363, y, 963, y), fill=(150, 150, 150))
    image.save(shot)
    audit = _browser_trace_audit(tmp_path, write=False)
    assert audit["browser_one_visible_row_after_handoff"]
    assert audit["candidates"][0]["action_id"] == "model-B-021"
    assert not (tmp_path / "browser_trace_audit.json").exists()


def test_unsaved_editor_buffer_is_detected_before_postscore_reopen():
    path = "/tmp/task/outputs/agent_B/qa_note.txt"
    assert _editor_has_unsaved_buffer("*qa_note.txt (/tmp/task) - gedit", path)
    assert not _editor_has_unsaved_buffer("qa_note.txt (/tmp/task) - gedit", path)


def test_input_lock_cannot_be_mislabeled_as_isolated_or_scripted(tmp_path):
    common = dict(case="build_verify", run_root=tmp_path / "unused",
                  provider=tmp_path, image="unused", runtime="unused",
                  base_url="http://127.0.0.1/v1", api_key_env="UNUSED",
                  mcp_python="python", model_timeout=1, diagnostic_step_limit=None,
                  negative=False, gui_input_lock=True)
    with pytest.raises(ValueError, match="Shared desktop"):
        run(condition="collaborative_isolated", model="test", **common)
    with pytest.raises(ValueError, match="Shared desktop"):
        run(condition="collaborative_shared", model=None, **common)
    assert not common["run_root"].exists()
