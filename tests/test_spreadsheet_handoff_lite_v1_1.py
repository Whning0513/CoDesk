"""Artifact correctness and protection controls for the independent Lite case."""
from __future__ import annotations

from pathlib import Path

import pytest

from oscombo.collab.data_to_deck.fixtures import _ods
from oscombo.collab.data_to_deck.live_pilot import run_pilot
from oscombo.collab.spreadsheet_handoff_lite_v1_1 import fixtures, live_pilot, oracle, spec
from oscombo.collab.spreadsheet_handoff_lite_v1_1.private.gold import expected_plan, write_gold


def test_version_and_units_are_unambiguous_without_gold_leakage():
    assert spec.CASE_VERSION == "1.1.0"
    assert fixtures.order_rows()[1][1:6] == [
        "Units per case", "USD per unit", "Budget USD", "ORDER UNITS", "Total cost USD"]
    assert "E3 is ORDER UNITS" in spec.AGENT_B_INSTRUCTION
    assert "E3 times C3" in spec.AGENT_B_INSTRUCTION
    assert "73" not in spec.AGENT_B_INSTRUCTION
    assert "80" not in spec.AGENT_B_INSTRUCTION
    assert "2240" not in spec.AGENT_B_INSTRUCTION


def test_versioned_entrypoint_and_lock_scope(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(live_pilot, "shared_runner_main", lambda argv: seen.extend(argv))
    live_pilot.main(["--condition", "collaborative_shared"])
    assert seen[:1] == ["--case-spreadsheet-lite-v1-1"]
    with pytest.raises(ValueError, match="separate Shared model ablation"):
        run_pilot("collaborative_isolated", tmp_path / "should-not-create", "unused", tmp_path,
                  "unused", model="dummy", case_spreadsheet_lite_v1_1=True,
                  gui_input_lock=True)
    assert not (tmp_path / "should-not-create").exists()


def _case(tmp_path: Path):
    root = tmp_path / "public"
    fixtures.build_fixture(root)
    source_a = root / spec.FIXTURE_NAMES["forecast"]
    source_b = root / spec.FIXTURE_NAMES["order"]
    saved_a, saved_b = tmp_path / "forecast.ods", tmp_path / "order_plan.ods"
    write_gold(saved_a, saved_b)
    return source_a, saved_a, source_b, saved_b


def test_gold_and_initial_negative_controls(tmp_path):
    source_a, saved_a, source_b, saved_b = _case(tmp_path)
    assert expected_plan() == (73, 80, 2240)
    score = oracle.evaluate(source_a, saved_a, source_b, saved_b)
    assert score["joint_success"] and score["protection_success"]
    assert not oracle.evaluate(source_a, source_a, source_b, source_b)["joint_success"]


def test_wrong_forecast_cannot_be_hidden_by_correct_order(tmp_path):
    source_a, saved_a, source_b, saved_b = _case(tmp_path)
    rows = fixtures.forecast_rows()
    rows[2][7:9] = [72, "B3:G3"]
    _ods(saved_a, {"Forecast": rows})
    score = oracle.evaluate(source_a, saved_a, source_b, saved_b)
    assert not score["actors"]["A"]["checks"]["correct_nonnegative_net_need"]
    assert not score["actors"]["B"]["checks"]["matches_saved_forecast"]


def test_wrong_pack_rounding_cost_and_source_are_rejected(tmp_path):
    source_a, saved_a, source_b, saved_b = _case(tmp_path)
    for units, cost, source_label, failed_check in [
        (8, 224, "forecast.ods", "correct_whole_case_order"),
        (73, 2044, "forecast.ods", "correct_whole_case_order"),
        (80, 2200, "forecast.ods", "correct_purchase_cost"),
        (80, 2240, "made-up.ods", "order_source_intact"),
    ]:
        rows = fixtures.order_rows()
        rows[2][4:7] = [units, cost, source_label]
        _ods(saved_b, {"Order": rows})
        score = oracle.evaluate(source_a, saved_a, source_b, saved_b)
        assert not score["joint_success"]
        assert not score["actors"]["B"]["checks"][failed_check]


def test_source_mutation_and_missing_evidence_are_rejected(tmp_path):
    source_a, saved_a, source_b, saved_b = _case(tmp_path)
    rows = fixtures.forecast_rows()
    rows[2][1] = 41
    rows[2][7:9] = [73, "B3:G3"]
    _ods(saved_a, {"Forecast": rows})
    assert not oracle.evaluate(source_a, saved_a, source_b, saved_b)["protection_success"]
    rows = fixtures.forecast_rows()
    rows[2][7:9] = [73, "trust me"]
    _ods(saved_a, {"Forecast": rows})
    assert not oracle.evaluate(source_a, saved_a, source_b, saved_b)["actors"]["A"]["success"]
