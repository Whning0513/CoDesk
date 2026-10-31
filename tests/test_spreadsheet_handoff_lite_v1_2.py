"""Independent v1.2 artifact correctness and no-answer public fixture controls."""
from __future__ import annotations

import zipfile
import shutil
import subprocess
from xml.etree import ElementTree as ET

import pytest
from oscombo.collab.data_to_deck.fixtures import NS, _ods
from oscombo.collab.data_to_deck.oracle import read_ods
from oscombo.collab.data_to_deck.live_pilot import _workspace_sync_audit
from oscombo.collab.spreadsheet_handoff_lite_v1_2 import fixtures, oracle, spec
from oscombo.collab.spreadsheet_handoff_lite_v1_2.audit_handoff import audit
from oscombo.collab.spreadsheet_handoff_lite_v1_2.bridge_audit import audit_bridge_history
from oscombo.collab.spreadsheet_handoff_lite_v1_2.check_resources import check as check_resources
from oscombo.collab.spreadsheet_handoff_lite_v1_2.verify_controls import verify as verify_controls
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
    write_json(tmp_path / "oracle.json", {"joint_success": True, "expected_need_evaluator_only": 73})
    events = [{"event": "peer_view_verified", "actor": "A", "revision": 1,
               "peer_view_path": view, "sha256": "sha1", "mode": "444", "time": 10},
              {"event": "revision_saved", "actor": "B", "revision": 1, "time": 20}]
    write_rows(tmp_path / "workspace_versions/events.jsonl", events)
    messages = [{"actor": "A", "recipient": "B", "message_id": "ready", "timestamp": 11,
                 "body": "Saved forecast is ready for review."}]
    write_rows(tmp_path / "collaboration/events.jsonl", messages)
    results = [
        {"type": "item.completed", "item": {"server": "collaboration", "tool": "list_saved_artifacts",
         "result": {"structured_content": {"A": a}}}},
        {"type": "item.completed", "item": {"server": "collaboration", "tool": "read_messages",
         "result": {"structured_content": {"result": [{"message_id": "ready"}]}}}},
    ]
    write_rows(tmp_path / "actor_runs/B/B/stdout.log", results)
    actions = [{"n": 1, "started_at": 3, "tool": "type_text", "args": {"text": "=E3*C3"}},
               {"n": 2, "screenshot_started_at": 15, "window_after": "forecast-r000001.ods - Calc"}]
    write_rows(tmp_path / "actor_runs/B/B/actions.jsonl", actions)
    shot = tmp_path / "actor_runs/B/B/shots/002.png"
    shot.parent.mkdir(parents=True); shot.write_bytes(b"placeholder for manual review")
    result = audit(tmp_path)
    assert result["peer_view_verified_readonly_and_delivered"]
    assert result["B_metadata_seen_stdout_index"] == 0
    assert result["B_formula_prework_candidate_actions"] == [1]
    assert result["B_saved_revision_after_view_candidate"]
    assert not result["visual_read_verified"]
    actions[1]["window_after"] = "forecast-r000000.ods - Calc"
    write_rows(tmp_path / "actor_runs/B/B/actions.jsonl", actions)
    assert not audit(tmp_path)["B_peer_view_screenshot_candidates"]
    messages[0]["body"] = "The answer is 73 units."
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
        "requested_guest_cpus": "8", "requested_guest_ram": "8G"}))
    host = {"disk_available_bytes": 20_000_000_000, "diskstats": "259 1 nvme", "cpu_stat": "cpu 1 2",
            "memory": {k: 1 for k in ("MemTotal_bytes", "MemAvailable_bytes", "SwapTotal_bytes", "SwapFree_bytes")}}
    sample = {"host": host, "guests": [{"container_id": "a", "qemu_config": {"cpus": "8", "memory": "8G"}},
                                        {"container_id": "b", "qemu_config": {"cpus": "8", "memory": "8G"}}]}
    path = tmp_path / "resource_samples.jsonl"
    path.write_text(json.dumps(sample) + "\n")
    assert check_resources(tmp_path, 2)["resource_observation_complete"]
    sample["guests"][1]["qemu_config"]["cpus"] = "4"
    path.write_text(json.dumps(sample) + "\n")
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
                                 "actors": {"B": {"checks": {"correct_whole_case_order": is_positive}}}}}
            values = {"result.json": result,
                      "workspace_sync_result.json": {"verified": True, "transient_errors": [],
                                                     "diagnostics": {"infrastructure_review_required": False},
                                                     "persistent_history": {"history_clean": True}},
                      "resource_profile_check.json": {"resource_observation_complete": True},
                      "scripted_peer_view.json": {"revision": 1, "sha256": "a", "peer_view_path": view,
                                                  "screenshot": "screenshots/view.png", "view_opened_at": 12},
                      "peer_view_visual_review.json": {"revision": 1, "view_path": view, "screenshot_sha256": sha,
                                                       "visible_H3_matches_scored_A": True, "reviewed_by": "reviewer",
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
    assert verify_controls(manifest, runs)["valid"]
    (runs / "positive-shared/screenshots/view.png").write_bytes(b"replaced")
    assert not verify_controls(manifest, runs)["valid"]
