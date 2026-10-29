"""Artifact correctness and protection controls for the independent Lite case."""
from __future__ import annotations

from pathlib import Path

from oscombo.collab.data_to_deck.fixtures import _ods
from oscombo.collab.spreadsheet_handoff_lite_v1 import fixtures, oracle, spec
from oscombo.collab.spreadsheet_handoff_lite_v1.private.gold import expected_plan, write_gold


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
