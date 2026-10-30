import json

import pytest

from oscombo.collab.workspace_assembly_lite_v1p2 import spec
from oscombo.collab.workspace_assembly_lite_v1p2.fixtures import build_fixture, report_odt
from oscombo.collab.workspace_assembly_lite_v1p2.oracle import evaluate

from oscombo.collab import lite_file_guest_pilot as pilot
from oscombo.collab.lite_file_guest_pilot import _profile, _scripted_actions


def test_positive_and_negative_artifacts(tmp_path):
    fixture = tmp_path / "fixture"
    manifest = build_fixture(fixture)
    assert manifest["case_version"] == "1.0.2"
    incoming = tmp_path / "incoming" / "inspection_note.txt"
    incoming.parent.mkdir()
    incoming.write_bytes((fixture / "inspection_note.txt").read_bytes())
    delivered = tmp_path / "delivery" / "inspection_note.txt"
    delivered.parent.mkdir()
    final = tmp_path / "final.odt"
    report_odt(final, "Delivered inspection_note.txt carries inspection tag RIVER-27.")
    incoming.rename(delivered)
    positive = evaluate(fixture / "inspection_note.txt", incoming, delivered,
                        fixture / "handoff_report.odt", final)
    assert positive["joint_success"]
    assert positive["case_version"] == "1.0.2"
    incoming.write_bytes(delivered.read_bytes())
    assert not evaluate(fixture / "inspection_note.txt", incoming, delivered,
                        fixture / "handoff_report.odt", final)["actors"]["A"]["success"]
    incoming.unlink()
    report_odt(final, "Delivered inspection_note.txt carries inspection tag WRONG.")
    assert not evaluate(fixture / "inspection_note.txt", incoming, delivered,
                        fixture / "handoff_report.odt", final)["actors"]["B"]["success"]


def test_v1p2_workflow_is_independent_and_gui_read_is_in_control():
    loaded, _, _ = _profile("workspace_assembly_v1p2")
    assert loaded is spec
    assert "First move" in spec.AGENT_A_INSTRUCTION
    assert "Then open the delivered note" in spec.AGENT_A_INSTRUCTION
    assert "coordinator will wake this same conversation" in spec.AGENT_B_INSTRUCTION
    steps = _scripted_actions("workspace_assembly_v1p2", "A", "/tmp/case", None, False)
    assert "ctrl','v" in steps[3]
    assert "press('enter')" in steps[4]
    assert "alt','f4" in steps[5]


def test_files_setup_requires_a_maximized_real_window(tmp_path, monkeypatch):
    class Guest:
        root = tmp_path
        guest_key = "shared"

        def screenshot(self, patience):
            assert patience == 45
            return b"test-frame"

    (tmp_path / "screenshots").mkdir()
    output = {"output": "0x100 0 70 101 1850 910 host incoming\n"}
    monkeypatch.setattr(pilot, "_guest_script", lambda guest, script, timeout: output)
    pilot._maximize_case7_files(Guest())
    assert (tmp_path / "screenshots/shared-files-maximized.png").read_bytes() == b"test-frame"
    output["output"] = "0x100 0 70 101 592 395 host incoming\n"
    with pytest.raises(RuntimeError, match="not maximized"):
        pilot._maximize_case7_files(Guest())

def test_scripted_read_checks_the_delivered_file_not_the_source(tmp_path):
    action = {"actor": "A", "action_id": "A-006",
              "code": "pyautogui.hotkey('alt','f4')",
              "window_before": {"output": "inspection_note.txt (/tmp/case/incoming) - gedit"}}
    path = tmp_path / "gui_actions.jsonl"
    path.write_text(json.dumps(action) + "\n")
    with pytest.raises(RuntimeError, match="did not open the delivered note"):
        pilot._audit_case7_scripted_delivered_read(tmp_path)
    action["window_before"]["output"] = "inspection_note.txt (/tmp/case/outputs/agent_A) - gedit"
    path.write_text(json.dumps(action) + "\n")
    result = pilot._audit_case7_scripted_delivered_read(tmp_path)
    assert result["delivered_note_opened_in_GUI"]
