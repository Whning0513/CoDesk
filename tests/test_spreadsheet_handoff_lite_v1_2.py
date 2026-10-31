"""Independent v1.2 artifact correctness and no-answer public fixture controls."""
from __future__ import annotations

import zipfile
import shutil
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from oscombo.collab.data_to_deck.fixtures import NS, _ods
from oscombo.collab.data_to_deck.oracle import read_ods
from oscombo.collab.data_to_deck.live_pilot import (
    _workspace_sync_audit, _spreadsheet_lite_v1_2_forecast_actions,
    _spreadsheet_lite_v1_2_prepare_actions, _spreadsheet_lite_v1_2_open_view_actions,
    _spreadsheet_lite_v1_2_order_actions,
)
from oscombo.collab.spreadsheet_handoff_lite_v1_2 import fixtures, oracle, spec
from oscombo.collab.spreadsheet_handoff_lite_v1_2 import live_pilot
from oscombo.collab.data_to_deck.live_pilot import run_pilot
from oscombo.collab.spreadsheet_handoff_lite_v1_2.audit_handoff import audit
from oscombo.collab.spreadsheet_handoff_lite_v1_2.bridge_audit import audit_bridge_history
from oscombo.collab.spreadsheet_handoff_lite_v1_2.check_resources import check as check_resources
from oscombo.collab.spreadsheet_handoff_lite_v1_2.verify_controls import verify as verify_controls
from oscombo.collab.spreadsheet_handoff_lite_v1_2.verify_pilot import verify as verify_pilot
from oscombo.collab.spreadsheet_handoff_lite_v1_2.guard_prior import check as guard_prior
from oscombo.collab.spreadsheet_handoff_lite_v1_2.private.gold import expected_plan, write_gold


def _case(tmp_path):
    public = tmp_path / "public"
    fixtures.build_fixture(public)
    source_a, source_b = (public / spec.FIXTURE_NAMES[k] for k in ("forecast", "order"))
    saved_a, saved_b = tmp_path / "forecast.ods", tmp_path / "order_plan.ods"
    write_gold(saved_a, saved_b)
    return source_a, saved_a, source_b, saved_b


def _set_formula(path, formula):
    with zipfile.ZipFile(path) as z:
        members = [(info, z.read(info.filename)) for info in z.infolist()]
    root = ET.fromstring(next(data for info, data in members if info.filename == "content.xml"))
    q = lambda ns, name: f"{{{NS[ns]}}}{name}"
    table = root.find(f".//{q('table','table')}")
    cell = table.findall(q("table", "table-row"))[2].findall(q("table", "table-cell"))[5]
    if formula is None:
        cell.attrib.pop(q("table", "formula"), None)
    else:
        cell.set(q("table", "formula"), formula)
    content = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(path, "w") as z:
        for info, data in members:
            z.writestr(info, content if info.filename == "content.xml" else data)


def test_public_fixture_has_blank_answers_and_versioned_layout(tmp_path):
    public = tmp_path / "public"
    manifest = fixtures.build_fixture(public)
    second = fixtures.build_fixture(tmp_path / "public_again")
    assert manifest["fixture_sha256"] == second["fixture_sha256"]
    forecast = read_ods(public / spec.FIXTURE_NAMES["forecast"])["Forecast"]
    order = read_ods(public / spec.FIXTURE_NAMES["order"])["Order"]
    assert forecast[2][7] == "" and order[2][4:6] == ["", ""]
    assert spec.CASE_VERSION == "1.2.0" and manifest["case_id"] == spec.CASE_ID
    assert "peer_view_path" in spec.AGENT_B_INSTRUCTION
    assert "do not include the computed number" in spec.AGENT_A_INSTRUCTION.lower()
    assert all(str(value) not in spec.AGENT_A_INSTRUCTION + spec.AGENT_B_INSTRUCTION
               for value in expected_plan())
    for key in ("forecast", "order"):
        with zipfile.ZipFile(public / spec.FIXTURE_NAMES[key]) as z:
            assert z.testzip() is None
            root = ET.fromstring(z.read("content.xml"))
            assert root.find(f".//{{{NS['style']}}}table-column-properties") is not None


def test_scripted_core_counts_each_physical_input_separately():
    paths = (_spreadsheet_lite_v1_2_forecast_actions(), _spreadsheet_lite_v1_2_prepare_actions(),
             _spreadsheet_lite_v1_2_open_view_actions("/tmp/sh12/views/B/forecast-r000001.ods"),
             _spreadsheet_lite_v1_2_order_actions(80))
    actions = [action for path in paths for action in path if action != "DONE"]
    assert len(actions) == 13
    assert all(action.count("pyautogui.") == 1 for action in actions)


def test_versioned_entrypoint_and_mutually_exclusive_cases(monkeypatch, tmp_path):
    received = []
    monkeypatch.setattr(live_pilot, "shared_runner_main", lambda args: received.extend(args))
    live_pilot.main(["--condition", "collaborative_shared"])
    assert received == ["--case-spreadsheet-lite-v1-2", "--condition", "collaborative_shared"]
    with pytest.raises(ValueError, match="select only one case version"):
        run_pilot("collaborative_shared", tmp_path / "no-run", "unused", tmp_path, "unused",
                  case_spreadsheet_lite_v1_1=True, case_spreadsheet_lite_v1_2=True)
    assert not (tmp_path / "no-run").exists()


@pytest.mark.parametrize("formula", ["of:=[.E3]*[.C3]", "of:=[.$C$3]*[.$E$3]",
                                     "of:=PRODUCT([.E3];[.C3])", "of:=([.E3]+[.E3])*[.C3]/2"])
def test_gold_and_equivalent_formula_controls(tmp_path, formula):
    source_a, saved_a, source_b, saved_b = _case(tmp_path)
    _set_formula(saved_b, formula)
    score = oracle.evaluate(source_a, saved_a, source_b, saved_b)
    assert score["joint_success"] and score["protection_success"]


@pytest.mark.parametrize("formula", [None, "of:=2240", "of:=[.E3]*28", "of:=[.E3]+[.C3]",
                                     "of:=[.E3]*[.C3]+1", "of:=[Other.A1]*[.C3]", "of:=1/0"])
def test_formula_negative_controls(tmp_path, formula):
    source_a, saved_a, source_b, saved_b = _case(tmp_path)
    _set_formula(saved_b, formula)
    score = oracle.evaluate(source_a, saved_a, source_b, saved_b)
    assert not score["actors"]["B"]["checks"]["general_cost_formula"]
    assert not score["joint_success"]


def test_wrong_need_cannot_be_hidden_by_correct_order(tmp_path):
    source_a, saved_a, source_b, saved_b = _case(tmp_path)
    rows = fixtures.forecast_rows(); rows[2][7] = 72
    _ods(saved_a, {"Forecast": rows})
    score = oracle.evaluate(source_a, saved_a, source_b, saved_b)
    assert not score["actors"]["A"]["checks"]["correct_nonnegative_net_need"]
    assert score["actors"]["B"]["local_success"]
    assert not score["joint_success"]


def test_B_local_success_is_independent_of_A_but_global_failure_is_reported(tmp_path):
    source_a, saved_a, source_b, saved_b = _case(tmp_path)
    a_rows = fixtures.forecast_rows(); a_rows[2][7] = 65
    _ods(saved_a, {"Forecast": a_rows})
    b_rows = fixtures.order_rows(); b_rows[2][4:6] = [70, 1960]
    _ods(saved_b, {"Order": b_rows}); _set_formula(saved_b, "of:=[.E3]*[.C3]")
    score = oracle.evaluate(source_a, saved_a, source_b, saved_b)
    assert not score["actors"]["A"]["success"]
    assert score["actors"]["B"]["local_success"]
    assert not score["actors"]["B"]["global_checks"]["correct_whole_case_order_for_true_need"]
    assert not score["joint_success"]


@pytest.mark.parametrize("row_count", [0, 1, 2])
@pytest.mark.parametrize("role", ["A", "B"])
def test_short_spreadsheet_is_an_explicit_task_failure(tmp_path, row_count, role):
    source_a, saved_a, source_b, saved_b = _case(tmp_path)
    rows, sheet = ((fixtures.forecast_rows(), "Forecast") if role == "A"
                   else (fixtures.order_rows(), "Order"))
    _ods(saved_a if role == "A" else saved_b, {sheet: rows[:row_count]})
    score = oracle.evaluate(source_a, saved_a, source_b, saved_b)
    assert not score["joint_success"] and score["invalid_artifact"] == "ValueError"


def test_blank_result_and_corrupt_archive_are_explicit_task_failures(tmp_path):
    source_a, saved_a, source_b, saved_b = _case(tmp_path)
    rows = fixtures.forecast_rows(); rows[2][7] = ""
    _ods(saved_a, {"Forecast": rows})
    assert not oracle.evaluate(source_a, saved_a, source_b, saved_b)["joint_success"]
    saved_a.write_bytes(b"not an ods archive")
    score = oracle.evaluate(source_a, saved_a, source_b, saved_b)
    assert not score["joint_success"] and score["invalid_artifact"] == "BadZipFile"


def test_host_io_failure_propagates_as_infrastructure_error(tmp_path, monkeypatch):
    source_a, saved_a, source_b, saved_b = _case(tmp_path)
    def unreadable(*args, **kwargs):
        raise PermissionError("cannot read collected artifact")
    monkeypatch.setattr(oracle, "_ods_rows", unreadable)
    with pytest.raises(PermissionError, match="cannot read collected artifact"):
        oracle.evaluate(source_a, saved_a, source_b, saved_b)


def test_case_count_and_wrong_cost_rejected(tmp_path):
    source_a, saved_a, source_b, saved_b = _case(tmp_path)
    for units, cost, rejected in ((8, 224, "correct_whole_case_order"),
                                  (80, 2200, "correct_purchase_cost")):
        write_gold(saved_a, saved_b)
        rows = fixtures.order_rows(); rows[2][4:6] = [units, cost]
        _ods(saved_b, {"Order": rows}); _set_formula(saved_b, "of:=[.E3]*[.C3]")
        score = oracle.evaluate(source_a, saved_a, source_b, saved_b)
        assert not score["actors"]["B"]["checks"][rejected]
        assert not score["joint_success"]


def test_source_mutation_and_initial_files_rejected(tmp_path):
    source_a, saved_a, source_b, saved_b = _case(tmp_path)
    assert not oracle.evaluate(source_a, source_a, source_b, source_b)["joint_success"]
    rows = fixtures.forecast_rows(); rows[2][1] = 41; rows[2][7] = 73
    _ods(saved_a, {"Forecast": rows})
    assert not oracle.evaluate(source_a, saved_a, source_b, saved_b)["protection_success"]


@pytest.mark.skipif(not shutil.which("libreoffice"), reason="LibreOffice unavailable on host")
def test_gold_formula_survives_libreoffice_roundtrip(tmp_path):
    source_a, saved_a, source_b, saved_b = _case(tmp_path)
    output = tmp_path / "roundtrip"
    output.mkdir()
    command = [shutil.which("libreoffice"),
               f"-env:UserInstallation={(tmp_path / 'lo-profile').as_uri()}",
               "--headless", "--convert-to", "ods", "--outdir", str(output),
               *(str(path) for path in (source_a, saved_a, source_b, saved_b))]
    subprocess.run(command, check=True, capture_output=True, text=True, timeout=90)
    score = oracle.evaluate(output / source_a.name, output / saved_a.name,
                            output / source_b.name, output / saved_b.name)
    assert score["joint_success"]


@pytest.mark.skipif(not shutil.which("libreoffice") or not Path("/usr/lib/python3/dist-packages/uno.py").exists(),
                    reason="Host LibreOffice UNO unavailable")
def test_initial_cell_selection_read_by_libreoffice_uno():
    completed = subprocess.run(["/usr/bin/python3", "-m",
        "oscombo.collab.spreadsheet_handoff_lite_v1_2.verify_fixture_uno"],
        check=True, capture_output=True, text=True, timeout=30)
    assert "selected=(7, 2)" in completed.stdout
    assert "selected=(5, 2)" in completed.stdout


def test_handoff_audit_rejects_stale_view_and_never_claims_visual_read(tmp_path):
    import json
    def write_json(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
    def write_rows(path, values):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(v) for v in values) + "\n")
    view = "views/B/forecast-r000001.ods"
    a = {"revision": 1, "sha256": "sha1", "peer_view_path": view, "delivered": True}
    write_json(tmp_path / "workspace_versions/current.json", {"A": a})
    write_json(tmp_path / "oracle.json", {"joint_success": False, "expected_need_evaluator_only": 73,
                                         "measured": {"saved_forecast_need": 65}})
    events = [{"event": "peer_view_verified", "actor": "A", "revision": 1,
               "peer_view_path": view, "sha256": "sha1", "mode": "444", "time": 10},
              {"event": "revision_saved", "actor": "B", "revision": 1, "time": 20},
              {"event": "peer_view_verified", "actor": "A", "revision": 1,
               "peer_view_path": view, "sha256": "sha1", "mode": "444", "time": 25}]
    write_rows(tmp_path / "workspace_versions/events.jsonl", events)
    messages = [{"actor": "A", "recipient": "B", "message_id": "ready", "timestamp": 11,
                 "body": "Saved forecast is ready for review."}]
    write_rows(tmp_path / "collaboration/events.jsonl", messages)
    results = [
        {"type": "item.started", "item": {"server": "desktop", "tool": "type_text"}},
        {"type": "item.completed", "item": {"server": "collaboration", "tool": "list_saved_artifacts",
         "result": {"structured_content": {"A": a}}}},
        {"type": "item.completed", "item": {"server": "collaboration", "tool": "read_messages",
         "result": {"structured_content": {"result": [{"message_id": "ready"}]}}}},
        {"type": "item.started", "item": {"server": "desktop", "tool": "key"}},
    ]
    write_rows(tmp_path / "actor_runs/B/B/stdout.log", results)
    actions = [{"n": 1, "started_at": 3, "screenshot_started_at": 4, "window_after": "order_plan.ods - Calc",
                "tool": "type_text", "args": {"text": "=E3*C3"}},
               {"n": 2, "screenshot_started_at": 15, "window_after": "forecast-r000001.ods - Calc"}]
    write_rows(tmp_path / "actor_runs/B/B/actions.jsonl", actions)
    shot = tmp_path / "actor_runs/B/B/shots/002.png"
    shot.parent.mkdir(parents=True); shot.write_bytes(b"placeholder for manual review")
    (shot.parent / "001.png").write_bytes(b"formula manual review")
    result = audit(tmp_path)
    assert result["peer_view_verified_readonly_and_delivered"]
    assert result["B_metadata_seen_stdout_index"] == 1
    assert result["B_formula_prework_candidate_actions"] == [1]
    assert result["B_formula_prework_screenshot_candidates"][0]["action"] == 1
    assert result["B_saved_revision_after_view_candidate"]
    assert not result["visual_read_verified"]
    actions[1]["tool"] = "screenshot"; actions[1]["window_after"] = None
    write_rows(tmp_path / "actor_runs/B/B/actions.jsonl", actions)
    assert audit(tmp_path)["B_peer_view_screenshot_candidates"][0]["candidate_basis"] == "explicit_screenshot"
    actions[1]["tool"] = "key"
    actions[1]["window_after"] = "forecast-r000000.ods - Calc"
    write_rows(tmp_path / "actor_runs/B/B/actions.jsonl", actions)
    assert not audit(tmp_path)["B_peer_view_screenshot_candidates"]
    messages[0]["body"] = "The saved answer is 65 units."
    write_rows(tmp_path / "collaboration/events.jsonl", messages)
    result = audit(tmp_path)
    assert result["A_explicit_numeric_result_in_message"]
    assert result["A_noncanonical_message_ids_for_manual_review"] == ["ready"]


def test_recovered_bridge_errors_are_not_silently_verified_in_v1_2():
    prior = ["RuntimeError: peer view failed"]
    failed = _workspace_sync_audit({"A": {"revision": 1}}, prior, strict=True,
                                   history={"history_clean": True},
                                   diagnostics={"infrastructure_review_required": True})
    assert failed["final_sync_ok"] and not failed["verified"]
    assert failed["transient_errors"] == prior
    assert not _workspace_sync_audit({}, [], strict=True)["verified"]
    assert _workspace_sync_audit({}, ["save retry"], strict=True, history={"history_clean": True},
                                 diagnostics={"infrastructure_review_required": False})["verified"]
    assert _workspace_sync_audit({}, prior, strict=False)["verified"]


def test_persistent_bridge_errors_and_unfinished_revisions_invalidate_even_after_restart(tmp_path):
    import json
    bridge = tmp_path / "bridge"; bridge.mkdir()
    versions = {"A": {"revision": 1, "delivered": True}, "B": {"revision": 0, "delivered": True}}
    event_file = bridge / "events.jsonl"
    event_file.write_text(json.dumps({"event": "revision_pending", "actor": "A", "revision": 1}) + "\n")
    (bridge / "pending-A.json").write_text(json.dumps([{"revision": 1, "sha256": "a"}]))
    clean = audit_bridge_history(bridge, versions)
    assert clean["history_clean"]
    event_file.write_text(event_file.read_text() + json.dumps({"event": "peer_view_error", "actor": "A"}) + "\n")
    history = audit_bridge_history(bridge, versions)
    assert history["persistent_errors"]
    assert not _workspace_sync_audit(versions, [], strict=True, history=history,
                                     diagnostics={"infrastructure_review_required": True})["verified"]
    event_file.write_text(json.dumps({"event": "revision_pending", "actor": "A"}) + "\n")
    (bridge / "pending-A.json").write_text(json.dumps([{"revision": 2, "sha256": "b"}]))
    assert audit_bridge_history(bridge, versions)["unresolved_pending"]
    (bridge / "pending-A.json").write_text("corrupt")
    assert audit_bridge_history(bridge, versions)["parse_errors"]


def test_resource_gate_requires_real_qemu_profile_and_host_observations(tmp_path):
    import json
    (tmp_path / "resource_profile.json").write_text(json.dumps({
        "requested_guest_cpus": "8", "requested_guest_ram": "8G", "sample_interval_s": 5}))
    (tmp_path / "provenance.json").write_text(json.dumps({"started_at": 1000}))
    (tmp_path / "result.json").write_text(json.dumps({"elapsed_s": 100}))
    host = {"disk_available_bytes": 20_000_000_000, "diskstats": "259 1 nvme", "cpu_stat": "cpu 1 2",
            "memory": {k: 1 for k in ("MemTotal_bytes", "MemAvailable_bytes", "SwapTotal_bytes", "SwapFree_bytes")}}
    sample = {"time": 1000, "host": host, "guests": [{"container_id": "a", "qemu_config": {"cpus": "8", "memory": "8G"}},
                                        {"container_id": "b", "qemu_config": {"cpus": "8", "memory": "8G"}}]}
    path = tmp_path / "resource_samples.jsonl"
    later = dict(sample, time=1050)
    final = dict(sample, time=1090)
    path.write_text("\n".join(json.dumps(x) for x in (sample, later, final)) + "\n")
    assert check_resources(tmp_path, 2)["resource_observation_complete"]
    sample["guests"][1]["qemu_config"]["cpus"] = "4"
    path.write_text("\n".join(json.dumps(x) for x in (sample, later, final)) + "\n")
    assert not check_resources(tmp_path, 2)["resource_observation_complete"]
    sample["guests"][1]["qemu_config"]["cpus"] = "8"
    path.write_text("\n".join(json.dumps(x) for x in (sample, later)) + "\n")
    assert not check_resources(tmp_path, 2)["resource_observation_complete"]
    path.unlink()
    assert not check_resources(tmp_path, 2)["resource_observation_complete"]


def test_control_gate_requires_all_topologies_and_review_of_exact_screenshot(tmp_path):
    import hashlib
    import json
    runs = tmp_path / "runs"; runs.mkdir()
    manifest = tmp_path / "controls.tsv"
    lines = ["control\tcondition\trun_id\texit_code"]
    for kind in ("positive", "wrong-units"):
        for side in ("shared", "isolated"):
            run_id = f"{kind}-{side}"; root = runs / run_id; root.mkdir()
            fixtures.build_fixture(root / "fixtures")
            is_positive = kind == "positive"
            (root / "screenshots").mkdir()
            screenshot = root / "screenshots/view.png"; screenshot.write_bytes(b"reviewable image")
            sha = hashlib.sha256(screenshot.read_bytes()).hexdigest()
            stale_shot = root / "screenshots/stale.png"; stale_shot.write_bytes(b"old image")
            stale_sha = hashlib.sha256(stale_shot.read_bytes()).hexdigest()
            view = "views/B/forecast-r000001.ods"
            stale_view = "views/B/forecast-r000000.ods"
            result = {"status": "PASS" if is_positive else "FAIL", "reopen_complete": True,
                      "reset": [{"workspace_clean": True}] * (2 if side == "isolated" else 1),
                      "oracle": {"joint_success": is_positive,
                                 "expected_need_evaluator_only": 73,
                                 "actors": {"B": {"checks": {"correct_whole_case_order": is_positive}}}}}
            values = {"result.json": result,
                      "provenance.json": {"source_commit": "a" * 40,
                                          "case_id": spec.CASE_ID, "case_version": spec.CASE_VERSION},
                      "workspace_sync_result.json": {"verified": True, "transient_errors": [],
                                                     "diagnostics": {"infrastructure_review_required": False},
                                                     "persistent_history": {"history_clean": True}},
                      "resource_profile_check.json": {"resource_observation_complete": True},
                      "scripted_peer_view.json": {"revision": 1, "sha256": "a", "peer_view_path": view,
                                                  "screenshot": "screenshots/view.png", "view_opened_at": 12},
                      "peer_view_visual_review.json": {"revision": 1, "view_path": view, "screenshot_sha256": sha,
                                                       "visible_H3_value": 73, "visible_H3_matches_scored_A": True, "reviewed_by": "reviewer",
                                                       "reviewed_at_utc": "2026-10-31T00:00:00Z"},
                      "scripted_stale_view.json": {"revision": 0, "sha256": "seed", "peer_view_path": stale_view,
                                                   "latest_revision": 1, "latest_sha256": "a", "stale_revision_rejected": True,
                                                   "screenshot": "screenshots/stale.png"},
                      "stale_view_visual_review.json": {"revision": 0, "view_path": stale_view,
                                                        "screenshot_sha256": stale_sha, "visible_H3_blank": True,
                                                        "reviewed_by": "reviewer", "reviewed_at_utc": "2026-10-31T00:00:00Z"}}
            for filename, data in values.items(): (root / filename).write_text(json.dumps(data))
            (root / "workspace_versions").mkdir()
            event = {"event": "peer_view_verified", "actor": "A", "revision": 1, "sha256": "a",
                     "peer_view_path": view, "mode": "444", "time": 10}
            seed_event = {"event": "peer_view_verified", "actor": "A", "revision": 0, "sha256": "seed",
                          "peer_view_path": stale_view, "mode": "444", "time": 1}
            (root / "workspace_versions/events.jsonl").write_text(json.dumps(seed_event) + "\n" + json.dumps(event) + "\n")
            lines.append(f"{kind}\t{side}\t{run_id}\t{0 if is_positive else 2}")
    manifest.write_text("\n".join(lines) + "\n")
    assert verify_controls(manifest, runs, "a" * 40)["valid"]
    assert not verify_controls(manifest, runs, "b" * 40)["valid"]
    (runs / "positive-shared/screenshots/view.png").write_bytes(b"replaced")
    assert not verify_controls(manifest, runs)["valid"]


def test_pilot_gate_checks_behavior_and_infrastructure_not_success_selection(tmp_path):
    import hashlib
    import json
    fixtures.build_fixture(tmp_path / "fixtures")
    shot = tmp_path / "actor_runs/B/B/shots/004.png"
    shot.parent.mkdir(parents=True); shot.write_bytes(b"visual evidence")
    sha = hashlib.sha256(shot.read_bytes()).hexdigest()
    prework_shot = shot.parent / "002.png"; prework_shot.write_bytes(b"formula evidence")
    prework_sha = hashlib.sha256(prework_shot.read_bytes()).hexdigest()
    view = "views/B/forecast-r000001.ods"
    values = {
        "provenance.json": {"source_commit": "a" * 40, "case_id": spec.CASE_ID,
            "case_version": spec.CASE_VERSION, "model": "gpt-6-astra", "effort": "medium",
            "actor_mcp_only": True, "diagnostic_step_limit": 18, "active_model_timeout_s": 900,
            "handoff_lifecycle": True, "yield_wait_lifecycle": True},
        "result.json": {"condition": "collaborative_isolated", "status": "FAIL", "reopen_complete": True,
                        "reset": [{"workspace_clean": True}, {"workspace_clean": True}],
                        "oracle": {"measured": {"saved_forecast_need": 65}}},
        "workspace_sync_result.json": {"verified": True, "diagnostics": {"infrastructure_review_required": False},
                                       "persistent_history": {"history_clean": True}},
        "resource_profile_check.json": {"resource_observation_complete": True},
        "handoff_audit.json": {"latest_A_revision": 1, "peer_view_path": view,
            "peer_view_verified_readonly_and_delivered": True, "A_ready_message_after_delivery": True,
            "A_explicit_numeric_result_in_message": False, "B_metadata_seen_stdout_index": 0,
            "B_message_read_stdout_index": 1, "B_formula_before_view_candidate_actions": [2],
            "B_formula_prework_screenshot_candidates": [{"screenshot": "actor_runs/B/B/shots/002.png"}],
            "B_saved_revision_after_view_candidate": True,
            "B_peer_view_screenshot_candidates": [{"screenshot": "actor_runs/B/B/shots/004.png"}]},
        "pilot_visual_review.json": {"revision": 1, "view_path": view, "screenshot": "actor_runs/B/B/shots/004.png",
            "screenshot_sha256": sha, "visible_H3_value": 65, "visible_H3_matches_saved_revision": True,
            "prework_screenshot": "actor_runs/B/B/shots/002.png", "prework_screenshot_sha256": prework_sha,
            "visible_F3_cost_formula": True,
            "A_messages_disclose_no_result": True, "reviewed_by": "reviewer", "reviewed_at_utc": "2026-10-31T00:00:00Z"},
        "actor_tool_boundary_audit.json": {"actors": {role: {"total_tool_calls": 2,
            "outside_gui_collaboration_contract": {}} for role in ("A", "B")}},
    }
    for name, value in values.items(): (tmp_path / name).write_text(json.dumps(value))
    (tmp_path / "codex_relay_events.jsonl").write_text("\n".join(json.dumps({"actor": role,
        "upstream_status": 200, "actor_mcp_only": True}) for role in ("A", "B")) + "\n")
    assert verify_pilot(tmp_path, "a" * 40)["gate_passed"]
    assert not verify_pilot(tmp_path, "b" * 40)["gate_passed"]
    shot.write_bytes(b"modified after review")
    assert not verify_pilot(tmp_path)["gate_passed"]


def test_model_runner_reads_private_credential_file_without_logging(tmp_path):
    import os
    # These tests launch a fake provider only. Avoid contending with a real
    # Case 6 experiment's host admission lock while checking credential flow.
    bin_dir = tmp_path / "bin"; bin_dir.mkdir()
    flock = bin_dir / "flock"; flock.write_text("#!/bin/sh\nexit 0\n"); flock.chmod(0o700)
    probe = tmp_path / "probe.json"
    osworld = tmp_path / "provider"
    python = osworld / ".venv/bin/python"; python.parent.mkdir(parents=True)
    python.write_text("#!/usr/bin/python3\nimport json,os,sys\n"
        "open(os.environ['CODESK_TEST_PROBE'],'w').write(json.dumps({"
        "'helper_key_absent':'AIGCBEST_API_KEY' not in os.environ,"
        "'cpus':os.environ.get('OSCOMBO_GUEST_CPUS'),'ram':os.environ.get('OSCOMBO_GUEST_RAM')}))\n"
        "sys.exit(3)\n")
    python.chmod(0o700)
    key = tmp_path / "private.key"; key.write_text("fixture-provider-key\n"); key.chmod(0o600)
    config = tmp_path / "env.sh"
    config.write_text(f"export OSWORLD_DIR={osworld}\nexport OSCOMBO_GUEST_IMAGE=/image\n"
                      "export OSCOMBO_RUNTIME_IMAGE=example\nexport AIGCBEST_API_KEY=decoy-env-key\n")
    env = {"PATH": f"{bin_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}", "CODESK_ENV_FILE": str(config),
           "CODESK_CASE6_KEY_FILE": str(key), "CODESK_CASE6_V12_CONTROLS_MANIFEST": str(tmp_path / "missing"),
           "CODESK_TEST_PROBE": str(probe)}
    completed = subprocess.run(["bash", "oscombo/collab/spreadsheet_handoff_lite_v1_2/run_model.sh", "pilot"],
                               env=env, capture_output=True, text=True, timeout=15)
    assert completed.returncode == 3
    assert "fixture-provider-key" not in completed.stdout + completed.stderr
    assert "decoy-env-key" not in completed.stdout + completed.stderr
    import json
    assert json.loads(probe.read_text()) == {"helper_key_absent": True, "cpus": "8", "ram": "8G"}


def test_only_model_driver_inherits_file_key_not_sampler_or_audits(tmp_path):
    import json
    import os
    repo = tmp_path / "repo"; repo.mkdir()
    (repo / "audits/three_lite_cases_20261029").mkdir(parents=True)
    (repo / "runs").mkdir()
    bin_dir = tmp_path / "bin"; bin_dir.mkdir()
    flock = bin_dir / "flock"; flock.write_text("#!/bin/sh\nexit 0\n"); flock.chmod(0o700)
    git = bin_dir / "git"
    git.write_text("#!/bin/sh\nif [ \"$2\" = --show-toplevel ]; then printf '%s\\n' \"$CODESK_TEST_REPO\"; "
                   "elif [ \"$1\" = rev-parse ]; then printf 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\\n'; fi\nexit 0\n")
    git.chmod(0o700)
    provider = tmp_path / "provider"; python = provider / ".venv/bin/python"; python.parent.mkdir(parents=True)
    python.write_text("#!/usr/bin/python3\nimport json,os,pathlib,sys,time\n"
        "mod=sys.argv[2] if len(sys.argv)>2 and sys.argv[1]=='-m' else ''\n"
        "probe=pathlib.Path(os.environ['CODESK_TEST_PROBE_DIR'])\n"
        "if mod.endswith('.live_pilot'):\n"
        " p=pathlib.Path(sys.argv[sys.argv.index('--run-root')+1]); p.mkdir(parents=True)\n"
        " (probe/'driver.json').write_text(json.dumps({'key_correct':os.environ.get('AIGCBEST_API_KEY')=='fixture-provider-key'}))\n"
        " time.sleep(0.8); sys.exit(3)\n"
        "if mod.endswith('.sample_resources') or mod.endswith('.check_resources'):\n"
        " (probe/(mod.rsplit('.',1)[-1]+'.json')).write_text(json.dumps({'key_absent':'AIGCBEST_API_KEY' not in os.environ}))\n"
        " sys.exit(3)\n"
        "sys.exit(3)\n")
    python.chmod(0o700)
    key = tmp_path / "private.key"; key.write_text("fixture-provider-key\n"); key.chmod(0o600)
    config = tmp_path / "env.sh"
    config.write_text(f"export OSWORLD_DIR={provider}\nexport OSCOMBO_GUEST_IMAGE=/image\n"
                      "export OSCOMBO_RUNTIME_IMAGE=example\nexport AIGCBEST_API_KEY=decoy-env-key\n")
    common = Path(__file__).resolve().parents[1] / "oscombo/collab/spreadsheet_handoff_lite_v1_2/run_common.sh"
    command = ('source "$1"; IFS= read -r AIGCBEST_API_KEY < "$CODESK_TEST_KEY"; '
               'export -n AIGCBEST_API_KEY; case6_preflight() { return 0; }; '
               'case6_run_case model collaborative_shared fixture-run 1 --model dummy || true')
    env = {"PATH": f"{bin_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}", "CODESK_ENV_FILE": str(config),
           "CODESK_TEST_REPO": str(repo), "CODESK_TEST_PROBE_DIR": str(tmp_path), "CODESK_TEST_KEY": str(key)}
    completed = subprocess.run(["bash", "-c", command, "test", str(common)], env=env,
                               capture_output=True, text=True, timeout=15)
    assert completed.returncode == 0
    assert "fixture-provider-key" not in completed.stdout + completed.stderr
    assert json.loads((tmp_path / "driver.json").read_text())["key_correct"]
    assert json.loads((tmp_path / "sample_resources.json").read_text())["key_absent"]
    assert json.loads((tmp_path / "check_resources.json").read_text())["key_absent"]
    assert "fixture-provider-key" not in (repo / "audits/three_lite_cases_20261029/fixture-run-driver.log").read_text()


def test_relay_actor_env_and_MCP_config_exclude_provider_key(tmp_path, monkeypatch):
    from oscombo.harness.base import AgentContext
    from oscombo.harness.external import CodexHarness
    class Guest:
        url = "http://127.0.0.1:5000"
    monkeypatch.setenv("CODESK_PROVIDER_TEST_KEY", "synthetic-provider-secret")
    monkeypatch.setenv("CODESK_RUN_RELAY_TOKEN", "synthetic-loopback-token")
    actor_spec = {"harness": "codex", "model": "gpt-6-astra", "options": {
        "base_url": "http://127.0.0.1:8000/v1", "api_key_env": "CODESK_RUN_RELAY_TOKEN",
        "redact_env_keys": ["CODESK_PROVIDER_TEST_KEY"], "codex_bin": "true"}}
    ctx = AgentContext(name="B", task_id="test", instruction="public", guest=Guest(),
                       out=tmp_path, max_steps=2, spec=actor_spec)
    harness = CodexHarness(actor_spec); harness.prepare(ctx)
    assert "CODESK_PROVIDER_TEST_KEY" not in harness.env(ctx)
    config = (tmp_path / "B/codex_home/config.toml").read_text()
    assert "synthetic-provider-secret" not in config
    assert "synthetic-provider-secret" not in repr(harness.env(ctx))


@pytest.mark.skipif(not Path("/data3/whn/Project2/OSWorld-V2/desktop_env/providers/docker/provider.py").exists(),
                    reason="Pinned OSWorld provider unavailable")
def test_guest_provider_environment_is_explicit_not_inherited(monkeypatch):
    import importlib
    import sys
    monkeypatch.syspath_prepend("/data3/whn/Project2/OSWorld-V2")
    module = importlib.import_module("desktop_env.providers.docker.provider")
    monkeypatch.setattr(module.docker, "from_env", lambda: object())
    monkeypatch.setenv("CODESK_PROVIDER_TEST_KEY", "synthetic-provider-secret")
    provider = module.DockerProvider("test")
    assert "CODESK_PROVIDER_TEST_KEY" not in provider.environment
    assert "synthetic-provider-secret" not in repr(provider.environment)


def test_round_guard_preserves_valid_failures_and_blocks_full_restart(tmp_path):
    import json
    audit_dir, runs = tmp_path / "audit", tmp_path / "runs"
    audit_dir.mkdir(); runs.mkdir(); commit = "a" * 40
    manifest = audit_dir / "case6-v1p2-triad1-20261031T000000Z-1.tsv"
    lines = ["mode\tarm\trun_id\texit_code\tdriver_exit_code"]
    for index, arm in enumerate(("isolated", "shared", "sharedlock")):
        run_id = f"run-{arm}"; root = runs / run_id; root.mkdir()
        fixtures.build_fixture(root / "fixtures")
        exit_code = "2" if index == 1 else "0"
        provenance = {"source_commit": commit, "case_id": spec.CASE_ID, "case_version": spec.CASE_VERSION,
                      "model": "gpt-6-astra", "effort": "medium", "endpoint": "https://api.haogpt.net/v1",
                      "model_request_retries": 2, "actor_mcp_only": True, "handoff_lifecycle": True,
                      "yield_wait_lifecycle": True, "active_model_timeout_s": 1200,
                      "effective_role_step_budget": {"A": 25, "B": 25}, "gui_input_lock": arm == "sharedlock"}
        (root / "provenance.json").write_text(json.dumps(provenance))
        (root / "result.json").write_text(json.dumps({"status": "FAIL" if exit_code == "2" else "PASS",
                                                       "condition": "collaborative_isolated" if arm == "isolated" else "collaborative_shared",
                                                       "reset": [{"workspace_clean": True}] * (2 if arm == "isolated" else 1),
                                                       "reopen_complete": True}))
        (root / "resource_profile_check.json").write_text('{"resource_observation_complete": true}')
        (root / "workspace_sync_result.json").write_text('{"verified": true}')
        (root / "actor_tool_boundary_audit.json").write_text(json.dumps({"actors": {role: {"total_tool_calls": 1,
            "outside_gui_collaboration_contract": {}} for role in ("A", "B")}}))
        (root / "codex_relay_events.jsonl").write_text("\n".join(json.dumps({"actor": role,
            "upstream_status": 200, "actor_mcp_only": True}) for role in ("A", "B")) + "\n")
        lines.append(f"triad1\t{arm}\t{run_id}\t{exit_code}\t{exit_code}")
    manifest.write_text("\n".join(lines) + "\n")
    status = guard_prior(audit_dir, runs, "triad1", commit)
    assert not status["safe_to_start_full_round"] and status["round_complete"]
    assert guard_prior(audit_dir, runs, "triad1", "b" * 40)["safe_to_start_full_round"]
    manifest.write_text("\n".join((lines[0], lines[2], lines[1], lines[3])) + "\n")
    assert not guard_prior(audit_dir, runs, "triad1", commit)["round_complete"]
    manifest.write_text("\n".join(lines) + "\n")
    (runs / "run-shared/result.json").unlink()
    status = guard_prior(audit_dir, runs, "triad1", commit)
    assert not status["round_complete"] and status["unreadable_prior_manifests"]
