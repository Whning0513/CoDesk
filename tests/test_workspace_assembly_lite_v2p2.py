"""Offline positive/negative controls for the independent short-entry Case 7."""
from __future__ import annotations

import ast
import base64
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

import pytest

from oscombo.collab import lite_file_guest_pilot as runner
from oscombo.collab.workspace_assembly_lite_v2p2 import audit, fixtures, oracle, scripted, spec
from oscombo.collab.workspace_assembly_lite_v2p2.private import gold


def _case(tmp_path: Path, code: str = "682"):
    fixture = tmp_path / "fixture"
    fixtures.build_fixture(fixture, inspection_tag=code)
    incoming = tmp_path / "incoming" / "inspection_note.txt"
    delivered = tmp_path / "delivery" / "inspection_note.txt"
    incoming.parent.mkdir()
    delivered.parent.mkdir()
    incoming.write_bytes((fixture / "inspection_note.txt").read_bytes())
    incoming.rename(delivered)
    report = tmp_path / "handoff_report.odt"

    def score():
        return oracle.evaluate(fixture / "inspection_note.txt", incoming, delivered,
                               fixture / "handoff_report.odt", report)

    return fixture, incoming, delivered, report, score


@pytest.mark.parametrize("code", ["682", "222", "975"])
def test_independent_fixture_gold_and_oracle_controls(tmp_path, code):
    fixture, incoming, delivered, report, score = _case(tmp_path, code)
    assert code not in spec.model_instruction("A") + spec.model_instruction("B")
    assert code not in (fixture / "case_brief.md").read_text()
    assert code not in oracle._odt_text((fixture / "handoff_report.odt").read_bytes())
    fixtures.report_odt(report, "Audience: Operations", f"Inspection code: {code}")
    assert score()["joint_success"] is True
    assert score()["actors"]["B"]["checks"]["source_line_preserved"] is True

    fixtures.report_odt(report, "Audience: Operations",
                        f"Inspection code: {fixtures.wrong_code(code)}")
    negative = score()
    assert negative["actors"]["A"]["success"] is True
    assert negative["actors"]["B"]["checks"]["code_matches_delivered"] is False
    assert negative["joint_success"] is False

    fixtures.report_odt(report, "Audience: Sales", f"Inspection code: {code}")
    wrong_audience = score()
    assert wrong_audience["actors"]["B"]["checks"]["audience_matches_draft"] is False
    assert wrong_audience["joint_success"] is False

    fixtures.report_odt(report, "Audience: OperationsInspection code: " + code)
    merged = score()
    assert merged["actors"]["B"]["checks"]["audience_matches_draft"] is False
    assert merged["actors"]["B"]["checks"]["code_present"] is False
    assert merged["actors"]["B"]["success"] is False

    fixtures.report_odt(report, "Audience: Operations", f"Inspection code: {code}")
    incoming.write_bytes(delivered.read_bytes())
    assert score()["actors"]["A"]["success"] is False
    incoming.unlink()
    delivered.write_bytes(fixtures.asset_text(fixtures.wrong_code(code)).encode())
    divergent = score()
    assert divergent["actors"]["A"]["success"] is False
    assert divergent["actors"]["B"]["success"] is False
    fixtures.report_odt(report, "Audience: Operations",
                        f"Inspection code: {fixtures.wrong_code(code)}")
    relative = score()
    assert relative["actors"]["B"]["success"] is True
    assert relative["actors"]["B"]["global_checks"]["code_matches_source"] is False
    assert relative["joint_success"] is False


def test_missing_delivery_and_malformed_report_are_separate(tmp_path):
    fixture, incoming, delivered, report, score = _case(tmp_path)
    fixtures.report_odt(report, "Audience: Operations", "Inspection code: 682")
    delivered.unlink()
    missing = score()
    assert missing["actors"]["A"]["success"] is False
    assert missing["actors"]["B"]["success"] is None
    delivered.write_bytes((fixture / "inspection_note.txt").read_bytes())
    with zipfile.ZipFile(report, "w") as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        archive.writestr("content.xml", "<broken")
    malformed = score()
    assert malformed["actors"]["A"]["success"] is True
    assert malformed["actors"]["B"]["success"] is False
    assert malformed["actors"]["B"]["artifact_error"] == "ParseError"


def test_scoring_side_gold_is_independent_and_not_in_public_fixture(tmp_path):
    fixture = tmp_path / "fixture"
    fixtures.build_fixture(fixture, inspection_tag="682")
    manifest = gold.build_gold(tmp_path / "gold", fixture)
    assert set(manifest) == {"inspection_note.txt", "handoff_report.odt"}
    assert not (fixture / "gold_manifest.json").exists()
    result = oracle.evaluate(fixture / "inspection_note.txt", tmp_path / "incoming-moved",
                             tmp_path / "gold/inspection_note.txt", fixture / "handoff_report.odt",
                             tmp_path / "gold/handoff_report.odt")
    assert result["joint_success"] is True


@pytest.mark.skipif(shutil.which("libreoffice") is None, reason="LibreOffice unavailable")
def test_writer_form_survives_offline_libreoffice_roundtrip(tmp_path):
    fixture = tmp_path / "fixture"
    fixtures.build_fixture(fixture, inspection_tag="682")
    source = tmp_path / "source"
    target = tmp_path / "converted"
    profile = tmp_path / "lo-profile"
    source.mkdir()
    target.mkdir()
    profile.mkdir()
    fixtures.report_odt(source / "handoff_report.odt", "Audience: Operations", "Inspection code: 682")
    done = subprocess.run(["libreoffice", f"-env:UserInstallation={profile.as_uri()}",
                           "--headless", "--convert-to", "odt", "--outdir", str(target),
                           str(source / "handoff_report.odt")], capture_output=True, timeout=45)
    assert done.returncode == 0
    text = oracle._odt_text((target / "handoff_report.odt").read_bytes())
    assert text.splitlines()[3:] == ["Audience: Operations", "Inspection code: 682"]
    delivered = tmp_path / "delivery" / "inspection_note.txt"
    delivered.parent.mkdir()
    delivered.write_bytes((fixture / "inspection_note.txt").read_bytes())
    result = oracle.evaluate(fixture / "inspection_note.txt", tmp_path / "incoming-moved",
                             delivered, fixture / "handoff_report.odt",
                             target / "handoff_report.odt")
    assert result["joint_success"] is True


def test_seeded_codes_are_short_distinct_and_not_in_public_instructions(tmp_path):
    seeds = [f"v2p2-round-{i}" for i in (1, 2, 3)]
    codes = [fixtures.tag_for_seed(seed) for seed in seeds]
    assert all(len(code) == 3 and set(code) <= set("23456789") for code in codes)
    assert len(set(codes)) == 3
    a = fixtures.build_fixture(tmp_path / "a", seed=seeds[0])
    b = fixtures.build_fixture(tmp_path / "b", seed=seeds[0])
    assert a["fixture_sha256"] == b["fixture_sha256"]
    assert a["case_version"] == "2.2.0"
    with pytest.raises(ValueError):
        fixtures.tag_for_seed("")


def test_adapter_is_versioned_and_scripted_inputs_are_short():
    assert runner._profile("workspace_assembly_v2p2") == (spec, fixtures, oracle)
    assert runner._case7_v2_module("workspace_assembly_v2p2", "scripted") is scripted
    assert runner._case7_v2_module("workspace_assembly_v2p2", "audit") is audit
    assert spec.TASK_ROOT == "/tmp/wa22"
    assert spec.PEER_VIEW_DIRS == {"A": "views/B"}
    assert len(scripted.a_move(spec.TASK_ROOT)[:-1]) == 3
    assert len(scripted.b_prepare("Operations")[:-1]) == 2
    assert len(scripted.b_read("/tmp/wa22/views/B/inspection_note-r000001.txt")[:-1]) == 2
    assert len(scripted.b_finish("682")[:-1]) == 4
    assert "press('enter')" not in scripted.b_finish("682")[1]
    assert " 682" in scripted.b_finish("682")[2]
    assert "peer_view_path" in spec.AGENT_B_INSTRUCTION
    assert "Do not inspect A's incoming or original output path" in spec.AGENT_B_INSTRUCTION

    groups = [scripted.a_move(spec.TASK_ROOT), scripted.b_prepare("Operations"),
              scripted.b_read("/tmp/wa22/views/B/inspection_note-r000001.txt"),
              scripted.b_finish("682")]
    calls = 0
    for group in groups:
        for action in group[:-1]:
            for node in ast.walk(ast.parse(action)):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and
                        isinstance(node.func.value, ast.Name) and node.func.value.id == "pyautogui"):
                    calls += 1
    assert calls == 15


def test_shared_and_isolated_install_same_public_source(tmp_path, monkeypatch):
    fixture = tmp_path / "fixture"
    fixtures.build_fixture(fixture, inspection_tag="682")
    scripts = []
    monkeypatch.setattr(runner, "_guest_script", lambda guest, script, timeout=45: scripts.append(script))
    for _ in ("A", "B", "shared"):
        runner._install(object(), fixture, spec.TASK_ROOT, "workspace_assembly_v2p2", spec)
    encoded_note = base64.b64encode((fixture / "inspection_note.txt").read_bytes()).decode("ascii")
    assert scripts[0] == scripts[1] == scripts[2]
    assert encoded_note in scripts[1]
    assert "incoming/inspection_note.txt" in scripts[1]
    assert "input/handoff_report.odt" in scripts[1]
    assert "input/case_brief.md" in scripts[1]


def test_trace_audit_accepts_prework_value_and_rejects_code_message_leak(tmp_path):
    fixtures.build_fixture(tmp_path / "fixtures", inspection_tag="682")
    for sub in ("workspace_versions", "collaboration", "actor_runs/B/B"):
        (tmp_path / sub).mkdir(parents=True)
    events = [
        {"event": "revision_committed", "actor": "B", "revision": 1, "time": 4, "sha256": "pre"},
        {"event": "peer_view_verified", "actor": "A", "revision": 1, "time": 9,
         "peer_view_path": "views/B/inspection_note-r000001.txt", "sha256": "abc", "mode": "444"},
        {"event": "revision_committed", "actor": "A", "revision": 1, "time": 10,
         "peer_view_path": "views/B/inspection_note-r000001.txt", "sha256": "abc"},
    ]
    actions = [
        {"n": 1, "executed": True, "tool": "type_text", "args": {"text": " Operations"},
         "action_started_at": 1, "window_before": "handoff_report.odt - LibreOffice Writer"},
        {"n": 2, "executed": True, "tool": "key", "args": {"keys": "ctrl+s"},
         "action_started_at": 2, "window_before": "handoff_report.odt - LibreOffice Writer"},
        {"n": 3, "executed": True, "tool": "type_text",
         "args": {"text": "/tmp/wa22/views/B/inspection_note-r000001.txt"}, "action_started_at": 11},
        {"n": 4, "tool": "key", "args": {"keys": "return"}, "action_started_at": 12,
         "window_after": "inspection_note-r000001.txt (read-only) - LibreOffice Writer"},
    ]
    def write(path, rows):
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    write(tmp_path / "workspace_versions/events.jsonl", events)
    write(tmp_path / "actor_runs/B/B/actions.jsonl", actions)
    message = {"type": "message", "actor": "A", "message_id": "m1", "body": "Revision 1 is ready."}
    write(tmp_path / "collaboration/events.jsonl", [message])
    evidence = audit.audit(tmp_path)
    assert evidence["B_prework_saved_before_A_publish"] is True
    assert evidence["B_typed_view_path_action_numbers"] == [3]
    assert evidence["B_readonly_view_window_action_numbers"] == [4]
    assert evidence["A_exact_code_leak_message_ids"] == []
    assert evidence["B_code_typed_before_A_publish_action_numbers"] == []
    actions[0]["args"]["text"] = " Operations 682"
    write(tmp_path / "actor_runs/B/B/actions.jsonl", actions)
    assert audit.audit(tmp_path)["B_code_typed_before_A_publish_action_numbers"] == [1]
    actions[0]["args"]["text"] = " Operations"
    write(tmp_path / "actor_runs/B/B/actions.jsonl", actions)
    message["body"] = "The code is 682."
    write(tmp_path / "collaboration/events.jsonl", [message])
    assert audit.audit(tmp_path)["A_exact_code_leak_message_ids"] == ["m1"]
