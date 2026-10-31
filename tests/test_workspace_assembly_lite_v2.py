import ast
import json
from pathlib import Path

import pytest

from oscombo.collab import lite_file_guest_pilot as pilot
from oscombo.collab.workspace_assembly_lite_v2 import audit, fixtures, oracle, scripted, spec


@pytest.mark.parametrize("tag", ["BIRCH-42", "CEDAR-17"])
def test_fixture_gold_and_positive_negative_controls(tmp_path, tag):
    fixture = tmp_path / "fixture"
    manifest = fixtures.build_fixture(fixture, inspection_tag=tag)
    assert manifest["case_id"] == "CDD-WA-LITE-002"
    assert manifest["case_version"] == "2.0.0"
    assert tag not in (fixture / "case_brief.md").read_text()
    assert tag not in spec.AGENT_A_INSTRUCTION + spec.AGENT_B_INSTRUCTION
    incoming = tmp_path / "incoming/inspection_note.txt"
    delivered = tmp_path / "delivery/inspection_note.txt"
    incoming.parent.mkdir()
    delivered.parent.mkdir()
    incoming.write_bytes((fixture / "inspection_note.txt").read_bytes())
    incoming.rename(delivered)
    report = tmp_path / "report.odt"
    fixtures.report_odt(report, "Audience: Operations.", f"Attachment: inspection_note.txt; tag {tag}.")
    def score():
        return oracle.evaluate(fixture / "inspection_note.txt", incoming, delivered,
                               fixture / "handoff_report.odt", report)
    assert score()["joint_success"] is True
    fixtures.report_odt(report, "For: operations team", f"inspection_note.txt carries {tag}")
    assert score()["joint_success"] is True
    fixtures.report_odt(report, "Audience: Operations.", "Attachment: inspection_note.txt; tag WRONG-00.")
    assert score()["actors"]["B"]["checks"]["tag_matches_source"] is False
    fixtures.report_odt(report, None, f"Attachment: inspection_note.txt; tag {tag}.")
    assert score()["actors"]["B"]["success"] is False
    fixtures.report_odt(report, "Audience: Operations.", f"Attachment: inspection_note.txt; tag {tag}.")
    incoming.write_bytes(delivered.read_bytes())
    assert score()["actors"]["A"]["checks"]["incoming_source_moved"] is False
    incoming.unlink()
    delivered.write_bytes(b"incorrect contents\n")
    assert score()["actors"]["A"]["checks"]["source_bytes_preserved"] is False


def test_oracle_separates_bad_fixture_from_malformed_actor_artifact(tmp_path):
    import zipfile
    fixture = tmp_path / "fixture"
    fixtures.build_fixture(fixture)
    delivered = tmp_path / "inspection_note.txt"
    delivered.write_bytes((fixture / "inspection_note.txt").read_bytes())
    final = tmp_path / "broken.odt"
    with zipfile.ZipFile(final, "w") as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        archive.writestr("content.xml", "<broken")
    score = oracle.evaluate(fixture / "inspection_note.txt", tmp_path / "missing", delivered,
                            fixture / "handoff_report.odt", final)
    assert score["actors"]["B"]["artifact_error"] == "ParseError" and not score["joint_success"]
    (fixture / "inspection_note.txt").unlink()
    score = oracle.evaluate(fixture / "inspection_note.txt", tmp_path / "missing", delivered,
                            fixture / "handoff_report.odt", final)
    assert score["invalid_fixture"] == "FileNotFoundError" and not score["joint_success"]


def test_oracle_scores_roles_independently_and_reports_host_io(tmp_path, monkeypatch):
    fixture = tmp_path / "fixture"
    fixtures.build_fixture(fixture)
    delivered = tmp_path / "inspection_note.txt"
    final = tmp_path / "report.odt"
    fixtures.report_odt(final, "Audience: Operations.", "Attachment: inspection_note.txt; tag BIRCH-42.")
    def score():
        return oracle.evaluate(fixture / "inspection_note.txt", tmp_path / "missing-incoming", delivered,
                               fixture / "handoff_report.odt", final)
    missing_a = score()
    assert missing_a["actors"]["A"]["success"] is False
    assert missing_a["actors"]["B"]["success"] is True and missing_a["joint_success"] is False
    delivered.write_bytes(b"wrong contents\n")
    wrong_a = score()
    assert not wrong_a["actors"]["A"]["success"] and wrong_a["actors"]["B"]["success"]
    delivered.write_bytes((fixture / "inspection_note.txt").read_bytes())
    final.unlink()
    missing_b = score()
    assert missing_b["actors"]["A"]["success"] and not missing_b["actors"]["B"]["success"]
    assert missing_b["actors"]["B"]["artifact_error"] == "FileNotFoundError"
    fixtures.report_odt(final, "Audience: Operations.", "Attachment: inspection_note.txt; tag BIRCH-42.")
    original = Path.read_bytes
    def deny_report(path):
        if path == final:
            raise PermissionError("synthetic host denial")
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", deny_report)
    denied = score()
    assert denied["invalid_scorer"] == "PermissionError"
    assert denied["actors"]["A"]["success"] is True and denied["actors"]["B"]["success"] is None
    assert denied["joint_success"] is None


def test_oracle_allows_blank_paragraphs_and_punctuation_but_not_fake_filename(tmp_path):
    import zipfile
    fixture = tmp_path / "fixture"
    fixtures.build_fixture(fixture)
    delivered = tmp_path / "inspection_note.txt"
    delivered.write_bytes((fixture / "inspection_note.txt").read_bytes())
    report = tmp_path / "report.odt"
    def score():
        return oracle.evaluate(fixture / "inspection_note.txt", tmp_path / "absent", delivered,
                               fixture / "handoff_report.odt", report)
    fixtures.report_odt(report, "Audience： Operations!", "Tag BIRCH-42; file inspection_note.txt.")
    with zipfile.ZipFile(report) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    members["content.xml"] = (members["content.xml"].replace(b"Aurora Supply Handoff</text:p>",
        b"Aurora Supply Handoff!</text:p>").replace(b"</text:p><text:p>", b"</text:p><text:p/><text:p>"))
    with zipfile.ZipFile(report, "w") as archive:
        for name, data in members.items(): archive.writestr(name, data)
    assert score()["actors"]["B"]["success"] is True
    for name in ("evilinspection_note.txt", "inspection_note.txt.backup"):
        fixtures.report_odt(report, "Audience: Operations", f"{name} has tag BIRCH-42.")
        assert score()["actors"]["B"]["checks"]["attachment_named"] is False


def test_profile_scripted_critical_path_and_short_root():
    loaded, fixture_module, _ = pilot._profile("workspace_assembly_v2")
    assert loaded is spec and fixture_module is fixtures
    assert spec.TASK_ROOT == "/tmp/wa2" and spec.PEER_VIEW_DIRS == {"A": "views/B"}
    assert len(scripted.a_move(spec.TASK_ROOT)[:-1]) == 3
    assert len(scripted.b_prepare("Operations")[:-1]) == 2
    assert len(scripted.b_read("/tmp/wa2/views/B/inspection_note-r000001.txt")[:-1]) == 2
    assert len(scripted.b_finish("BIRCH-42")[:-1]) == 4
    assert "Audience: Operations." in scripted.b_prepare("Operations")[0]
    assert "press('enter')" in scripted.b_finish("BIRCH-42")[1]
    assert "only a notification" in spec.AGENT_A_INSTRUCTION
    assert "peer_view_path" in spec.AGENT_B_INSTRUCTION
    assert "Do not inspect A's incoming or original output path" in spec.AGENT_B_INSTRUCTION


def test_seeded_fixture_is_deterministic_and_changes_between_rounds(tmp_path):
    seeds = ["codesk-wa-v2-round1-20261031", "codesk-wa-v2-round2-20261031",
             "codesk-wa-v2-round3-20261031"]
    tags = [fixtures.tag_for_seed(seed) for seed in seeds]
    assert len(set(tags)) == 3
    left = fixtures.build_fixture(tmp_path / "left", seed=seeds[0])
    right = fixtures.build_fixture(tmp_path / "right", seed=seeds[0])
    other = fixtures.build_fixture(tmp_path / "other", seed=seeds[1])
    assert left["fixture_sha256"] == right["fixture_sha256"]
    assert left["fixture_sha256"]["inspection_note.txt"] != other["fixture_sha256"]["inspection_note.txt"]
    assert all(tag not in spec.AGENT_A_INSTRUCTION + spec.AGENT_B_INSTRUCTION for tag in tags)
    assert all(tag not in (tmp_path / "left/case_brief.md").read_text() for tag in tags)
    with pytest.raises(ValueError):
        fixtures.tag_for_seed("")


def test_critical_path_counts_physical_gui_inputs_not_compound_calls():
    groups = {"A_move": scripted.a_move(spec.TASK_ROOT),
              "B_prework": scripted.b_prepare("Operations"),
              "B_open": scripted.b_read("/tmp/wa2/views/B/inspection_note-r000001.txt"),
              "B_finish": scripted.b_finish("BIRCH-42")}
    counts = {}
    for name, actions in groups.items():
        count = 0
        for action in actions:
            if action == "DONE":
                continue
            tree = ast.parse(action)
            for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
                fn = call.func
                if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) and fn.value.id == "pyautogui":
                    assert fn.attr in {"hotkey", "press", "write"}
                    assert not any(kw.arg == "presses" for kw in call.keywords)
                    count += 1
        counts[name] = count
    assert counts == {"A_move": 5, "B_prework": 2, "B_open": 4, "B_finish": 4}
    assert sum(counts.values()) == 15


def test_install_prepares_identical_peer_view_parent_per_guest(tmp_path, monkeypatch):
    fixture = tmp_path / "fixture"
    fixtures.build_fixture(fixture)
    scripts = []
    monkeypatch.setattr(pilot, "_guest_script", lambda guest, script, timeout=45: scripts.append(script))
    for guest in (object(), object()):
        pilot._install(guest, fixture, spec.TASK_ROOT, "workspace_assembly_v2", spec)
    assert len(scripts) == 2 and scripts[0] == scripts[1]
    assert "mkdir -p /tmp/wa2/views/B" in scripts[0]
    assert "private" not in scripts[0]


def test_trace_audit_records_prework_view_and_message_leak_separately(tmp_path):
    fixtures.build_fixture(tmp_path / "fixtures", inspection_tag="CEDAR-17")
    for sub in ("workspace_versions", "collaboration", "actor_runs/B/B"):
        (tmp_path / sub).mkdir(parents=True)
    def write(path, rows):
        path.write_text("".join(json.dumps(x) + "\n" for x in rows))
    events = [
        {"event": "revision_committed", "actor": "B", "revision": 1, "time": 4, "sha256": "pre"},
        {"event": "peer_view_verified", "actor": "A", "revision": 1, "time": 9,
         "peer_view_path": "views/B/inspection_note-r000001.txt", "sha256": "abc", "mode": "444"},
        {"event": "revision_committed", "actor": "A", "revision": 1, "time": 10,
         "peer_view_path": "views/B/inspection_note-r000001.txt", "sha256": "abc"}]
    write(tmp_path / "workspace_versions/events.jsonl", events)
    actions = [
        {"n": 1, "executed": True, "tool": "type_text", "args": {"text": "Audience: Operations."}, "action_started_at": 1,
         "window_before": "handoff_report.odt - LibreOffice Writer"},
        {"n": 2, "executed": True, "tool": "key", "args": {"keys": "ctrl+s"}, "action_started_at": 2,
         "window_before": "handoff_report.odt - LibreOffice Writer"},
        {"n": 3, "executed": True, "tool": "type_text", "args": {"text": "/tmp/wa2/views/B/inspection_note-r000001.txt"}, "action_started_at": 11},
        {"n": 4, "tool": "key", "args": {"keys": "return"}, "action_started_at": 12,
         "window_after": "inspection_note-r000001.txt (read-only) - LibreOffice Writer"}]
    write(tmp_path / "actor_runs/B/B/actions.jsonl", actions)
    msg = {"type": "message", "actor": "A", "message_id": "m1", "body": "Revision 1 is ready."}
    write(tmp_path / "collaboration/events.jsonl", [msg])
    result = audit.audit(tmp_path)
    assert result["B_prework_saved_before_A_publish"]
    assert result["peer_view_sha_mode_event_verified"]
    assert result["B_typed_view_path_action_numbers"] == [3]
    assert result["B_readonly_view_window_action_numbers"] == [4]
    assert result["A_exact_tag_leak_message_ids"] == []
    assert result["manual_screenshot_review_required"]
    actions[0]["window_before"] = "inspection_note.txt - gedit"
    write(tmp_path / "actor_runs/B/B/actions.jsonl", actions)
    assert not audit.audit(tmp_path)["B_prework_saved_before_A_publish"]
    actions[0]["window_before"] = "handoff_report.odt - LibreOffice Writer"
    actions.append({"n": 5, "tool": "type_text", "args": {"text": "/tmp/wa2/input/inspection_note.txt"},
                    "action_started_at": 14})
    write(tmp_path / "actor_runs/B/B/actions.jsonl", actions)
    assert audit.audit(tmp_path)["B_original_input_path_action_candidates"] == [5]
    msg["body"] = "Revision 1 has CEDAR-17."
    write(tmp_path / "collaboration/events.jsonl", [msg])
    assert audit.audit(tmp_path)["A_exact_tag_leak_message_ids"] == ["m1"]


def test_resource_audit_requires_actual_qemu_configuration_and_complete_samples(tmp_path):
    from oscombo.collab.workspace_assembly_lite_v2 import resource_sampler
    root = tmp_path / "run"
    root.mkdir()
    meta = {"started_at": 0, "guest_resources_requested": {"cpus": "8", "ram": "8G"},
            "guest_count": 2, "guests": [{"container_id": "a"}, {"container_id": "b"}]}
    (root / "provenance.json").write_text(json.dumps(meta))
    (root / "result.json").write_text(json.dumps({"elapsed_s": 10}))
    def guest(cid):
        return {"container_id": cid, "argv": ["qemu-system-x86_64", "-m", "8G", "-smp", "8"],
                "rss_and_io": {"VmRSS": "10 kB", "VmSwap": "0 kB", "read_bytes": "0", "write_bytes": "0"}}
    row = {"guests": [guest("a"), guest("b")],
           "host_meminfo": {"MemAvailable": "9 kB", "SwapTotal": "10 kB", "SwapFree": "9 kB"},
           "host_io_pressure": "some avg10=0.00"}
    samples = root / "resource_samples_v2.jsonl"
    samples.write_text("".join(json.dumps({**row, "time": t}) + "\n" for t in (0, 10)))
    assert resource_sampler.summarize(root)["valid"] is True
    samples.write_text(json.dumps({**row, "time": 0}) + "\n")
    assert resource_sampler.summarize(root)["valid"] is False
    samples.write_text("".join(json.dumps({**row, "time": t}) + "\n" for t in (0, 100)))
    assert resource_sampler.summarize(root)["valid"] is False
    row["guests"][1]["argv"][-1] = "4"
    samples.write_text("".join(json.dumps({**row, "time": t}) + "\n" for t in (0, 10)))
    assert resource_sampler.summarize(root)["valid"] is False
    row["guests"][1]["argv"][-1] = "8"
    del row["guests"][1]["rss_and_io"]["VmSwap"]
    samples.write_text("".join(json.dumps({**row, "time": t}) + "\n" for t in (0, 10)))
    assert resource_sampler.summarize(root)["valid"] is False


def test_metrics_exclude_multiple_waits_and_count_lock_overlaps(tmp_path):
    from oscombo.collab.workspace_assembly_lite_v2 import analyze
    root = tmp_path / "run"
    root.mkdir()
    def write_json(name, obj):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj))
    def write_rows(name, items):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(item) + "\n" for item in items))
    write_json("provenance.json", {"started_at": 0})
    write_json("result.json", {"status": "PASS", "oracle": {"joint_success": True}, "elapsed_s": 110})
    write_rows("actors.jsonl", [{"actor": "A", "started_at": 0, "ended_at": 100, "status": "done"},
                                {"actor": "B", "started_at": 10, "ended_at": 90, "status": "done"}])
    write_rows("actor_lifecycle.jsonl", [
        {"actor": "B", "event": "suspended_for_peer_handoff", "time": 20},
        {"actor": "B", "event": "woken_by_peer_handoff", "time": 40},
        {"actor": "B", "event": "suspended_for_peer_handoff", "time": 50},
        {"actor": "B", "event": "woken_by_peer_handoff", "time": 60}])
    for role, intervals in {"A": [(12, 14), (60, 64)], "B": [(13, 15), (61, 62)]}.items():
        write_rows(f"actor_runs/{role}/{role}/actions.jsonl", [
            {"executed": True, "action_started_at": x, "action_ended_at": y,
             "input_lock": {"enabled": True, "wait_s": 0.25, "held_s": y - x}}
            for x, y in intervals])
    write_rows("codex_relay_events.jsonl", [
        {"actor": "A", "started_at": 1, "time": 5, "upstream_status": 200,
         "elapsed_s": 4, "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}},
        {"actor": "B", "started_at": 3, "time": 7, "upstream_status": 200,
         "elapsed_s": 4, "usage": {"input_tokens": 20, "output_tokens": 3, "total_tokens": 23}}])
    write_rows("resource_samples_v2.jsonl", [{"disk_available_bytes": 123, "guests": [],
        "host_meminfo": {"SwapTotal": "10 kB", "SwapFree": "8 kB"}}])
    out = analyze.analyze(root)
    assert out["suspended_wait_s"]["B"] == 30
    assert out["active_overlap_s"] == 50
    assert out["gui_input_overlap_s"] == 2
    assert out["model_request_overlap_s"] == 2
    assert out["actors"]["A"]["lock_wait_s"] == 0.5
    assert out["actors"]["B"]["total_tokens"] == 23
    assert out["host_peak_swap_used_bytes"] == 2048


def test_model_contract_checks_actual_tools_and_transport(tmp_path):
    from oscombo.collab.workspace_assembly_lite_v2 import contract
    def write_rows(path, items):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(item) + "\n" for item in items))
    relay = [{"actor": actor, "actor_mcp_only": True, "upstream_status": 200} for actor in "AB"]
    write_rows(tmp_path / "codex_relay_events.jsonl", relay)
    for actor in "AB":
        item = {"id": "one", "type": "mcp_tool_call", "server": "desktop", "tool": "screenshot"}
        write_rows(tmp_path / f"actor_runs/{actor}/{actor}/stdout.log", [
            {"type": "item.started", "item": item}, {"type": "item.completed", "item": item}])
    clean = contract.audit(tmp_path)
    assert clean["valid"] and clean["actor_tool_calls"]["A:mcp_tool_call:desktop"] == 1
    path = tmp_path / "actor_runs/B/B/stdout.log"
    with path.open("a") as stream:
        stream.write(json.dumps({"type": "item.started", "item": {"id": "two", "type": "command_execution"}}) + "\n")
    assert not contract.audit(tmp_path)["valid"]
    relay[0]["upstream_status"] = None
    write_rows(tmp_path / "codex_relay_events.jsonl", relay)
    assert any("transport" in error for error in contract.audit(tmp_path)["errors"])


def test_postscore_closed_writer_restore_requires_absent_window(monkeypatch):
    from oscombo.collab import lite_file_guest_pilot as pilot
    guest = object()
    calls = []
    def activate(*args):
        calls.append("activate")
        if calls.count("activate") == 1:
            raise RuntimeError("no active window")
    monkeypatch.setattr(pilot, "_activate", activate)
    monkeypatch.setattr(pilot, "_launch", lambda *args: calls.append("launch"))
    monkeypatch.setattr(pilot, "_guest_script", lambda *args, **kwargs: {"status": "success", "output": "other"})
    assert pilot._restore_closed_case7_writer(guest, "/tmp/handoff_report.odt", "run") is True
    assert calls == ["activate", "launch", "activate"]
    calls.clear()
    monkeypatch.setattr(pilot, "_guest_script", lambda *args, **kwargs: {"status": "success", "output": "handoff_report.odt"})
    with pytest.raises(RuntimeError, match="exists"):
        pilot._restore_closed_case7_writer(guest, "/tmp/handoff_report.odt", "run")
    assert calls == ["activate"]
