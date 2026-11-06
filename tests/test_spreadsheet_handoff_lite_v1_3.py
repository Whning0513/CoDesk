"""Offline positive/negative controls for Spreadsheet Handoff Lite v1.3."""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from oscombo.collab.data_to_deck.fixtures import NS, _ods
from oscombo.collab.data_to_deck.oracle import read_ods
from oscombo.collab.spreadsheet_handoff_lite_v1_3 import fixtures, oracle, spec
from oscombo.collab.spreadsheet_handoff_lite_v1_3.private.gold import (
    A_NEED_FORMULA, B_COST_FORMULA, B_UNITS_FORMULA, expected_plan, write_gold,
)


def _case(tmp_path: Path):
    public = tmp_path / "public"
    manifest = fixtures.build_fixture(public)
    source_a = public / spec.FIXTURE_NAMES["forecast"]
    source_b = public / spec.FIXTURE_NAMES["order"]
    saved_a, saved_b = tmp_path / "saved_forecast.ods", tmp_path / "saved_order.ods"
    write_gold(saved_a, saved_b)
    return source_a, saved_a, source_b, saved_b, manifest


def _rewrite_forecast(path: Path, need: object, formula: str = A_NEED_FORMULA) -> None:
    rows = fixtures.forecast_rows()
    if len(rows[2]) <= 7:
        rows[2].append(need)
    else:
        rows[2][7] = need
    _ods(path, {"Forecast": rows})
    if formula is not None:
        fixtures._set_formula(path, "Forecast", 3, 8, formula)


def _rewrite_order(path: Path, need: object, cartons: object, units: object, cost: object,
                   units_formula: str = B_UNITS_FORMULA,
                   cost_formula: str = B_COST_FORMULA) -> None:
    rows = fixtures.order_rows()
    rows[2][4:8] = [need, cartons, units, cost]
    _ods(path, {"Order": rows})
    if units_formula is not None:
        fixtures._set_formula(path, "Order", 3, 7, units_formula)
    if cost_formula is not None:
        fixtures._set_formula(path, "Order", 3, 8, cost_formula)


def _score(paths):
    return oracle.evaluate(*paths[:4])


def test_fixture_is_deterministic_answer_free_and_explicit_about_units(tmp_path):
    first = fixtures.build_fixture(tmp_path / "first")
    second = fixtures.build_fixture(tmp_path / "second")
    assert first["fixture_sha256"] == second["fixture_sha256"]
    assert first["case_id"] == "CDD-SH-LITE-003"
    forecast = read_ods(tmp_path / "first" / spec.FIXTURE_NAMES["forecast"])["Forecast"]
    order = read_ods(tmp_path / "first" / spec.FIXTURE_NAMES["order"])["Order"]
    assert len(forecast[2]) == 7  # trailing empty H3 is omitted by the ODS reader
    assert order[2][4:6] == [0, 0]
    assert order[2][6:8] == [0, 0]
    assert "CARTONS" in " ".join(order[1]).upper()
    assert "INDIVIDUAL UNITS" in " ".join(order[1]).upper()
    assert "do not send the number" in spec.AGENT_A_INSTRUCTION.lower()
    assert all(str(value) not in spec.AGENT_A_INSTRUCTION + spec.AGENT_B_INSTRUCTION
               for value in expected_plan())


def test_gold_positive_control_passes_all_oracle_checks(tmp_path):
    paths = _case(tmp_path)
    score = _score(paths)
    assert expected_plan() == (73, 8, 80, 2240)
    assert score["joint_success"] and score["protection_success"]
    assert score["actors"]["A"]["success"]
    assert score["actors"]["B"]["success"]
    assert score["actors"]["B"]["global_success"]


def test_algebraically_equivalent_a_formula_is_accepted(tmp_path):
    paths = _case(tmp_path)
    equivalent = "of:=MAX(0;((([.B3]+[.C3]+[.D3])*(2/3))+[.G3])-[.E3]-[.F3])"
    _rewrite_forecast(paths[1], 73, equivalent)
    score = _score(paths)
    assert score["actors"]["A"]["checks"]["formula_uses_sales_stock_inbound_and_safety_inputs"]
    assert score["joint_success"]


def test_wrong_forecast_cannot_be_hidden_by_b_decision(tmp_path):
    paths = _case(tmp_path)
    wrong = "of:=MAX(0;([.B3]+[.C3]+[.D3])/3*2+[.G3]-[.E3]-[.F3]-8)"
    _rewrite_forecast(paths[1], 65, wrong)
    _rewrite_order(paths[3], 65, 7, 70, 1960)
    score = _score(paths)
    assert not score["actors"]["A"]["success"]
    assert score["actors"]["B"]["local_success"]
    assert not score["actors"]["B"]["global_checks"]["correct_cartons_for_true_need"]
    assert not score["joint_success"]


@pytest.mark.parametrize("formula,value", [
    ("of:=73", 73),
    ("of:=MAX(0;([.B3]*0)+([.C3]*0)+([.D3]*0)+([.E3]*0)+([.F3]*0)+([.G3]*0)+73)", 73),
    ("of:=MAX(0;([.B3]+[.C3]+[.D3])/3*2+[.G3]-[.E3])", 91),
])
def test_a_wrong_or_answer_only_formula_is_rejected(tmp_path, formula, value):
    paths = _case(tmp_path)
    _rewrite_forecast(paths[1], value, formula)
    score = _score(paths)
    assert not score["actors"]["A"]["checks"]["formula_uses_sales_stock_inbound_and_safety_inputs"]
    assert not score["joint_success"]


def test_cases_units_confusion_is_rejected(tmp_path):
    paths = _case(tmp_path)
    # B writes the needed 80 individual units into the field explicitly labeled cartons.
    _rewrite_order(paths[3], 73, 80, 800, 22400)
    score = _score(paths)
    assert score["actors"]["A"]["success"]
    assert not score["actors"]["B"]["checks"]["correct_minimum_whole_carton_count"]
    assert not score["actors"]["B"]["checks"]["within_budget_cap"]
    assert not score["joint_success"]


def test_insufficient_cartons_and_wrong_cost_formula_are_rejected(tmp_path):
    paths = _case(tmp_path)
    _rewrite_order(paths[3], 73, 7, 70, 1960)
    score = _score(paths)
    assert not score["actors"]["B"]["checks"]["correct_minimum_whole_carton_count"]
    assert not score["joint_success"]

    paths = _case(tmp_path / "second")
    _rewrite_order(paths[3], 73, 8, 80, 2240,
                   cost_formula="of:=[.G3]*[.C3]+1")
    score = _score(paths)
    assert not score["actors"]["B"]["checks"]["calculated_total_cost"]
    assert not score["joint_success"]


def test_source_changes_and_missing_formula_fail_protection_or_scoring(tmp_path):
    paths = _case(tmp_path)
    changed_order = fixtures.order_rows()
    changed_order[2][1] = 12
    _ods(paths[2], {"Order": changed_order})
    score = _score(paths)
    assert not score["protection_success"]
    assert not score["joint_success"]

    paths = _case(tmp_path / "second")
    _rewrite_forecast(paths[1], 73, formula=None)
    score = _score(paths)
    assert not score["actors"]["A"]["checks"]["formula_uses_sales_stock_inbound_and_safety_inputs"]
    assert not score["joint_success"]


def test_initial_workbooks_and_corrupt_ods_are_rejected(tmp_path):
    paths = _case(tmp_path)
    score = oracle.evaluate(paths[0], paths[0], paths[2], paths[2])
    assert not score["joint_success"]

    paths[1].write_bytes(b"not an ODS archive")
    score = _score(paths)
    assert not score["joint_success"]
    assert score["invalid_artifact"] == "BadZipFile"


def test_host_permission_error_propagates_as_infrastructure_failure(tmp_path, monkeypatch):
    paths = _case(tmp_path)

    def unreadable(*args, **kwargs):
        raise PermissionError("cannot read scored ODS")

    monkeypatch.setattr(oracle, "_rows", unreadable)
    with pytest.raises(PermissionError, match="cannot read scored ODS"):
        _score(paths)


@pytest.mark.skipif(not shutil.which("libreoffice"), reason="LibreOffice unavailable")
def test_gold_formula_and_values_survive_libreoffice_roundtrip(tmp_path):
    paths = _case(tmp_path)
    source_forecast, saved_forecast, source_order, saved_order = paths[:4]
    output = tmp_path / "roundtrip"
    output.mkdir()
    command = [
        shutil.which("libreoffice"),
        f"-env:UserInstallation={(tmp_path / 'lo-profile').as_uri()}",
        "--headless", "--convert-to", "ods", "--outdir", str(output),
        str(source_forecast), str(saved_forecast), str(source_order), str(saved_order),
    ]
    import subprocess
    subprocess.run(command, check=True, capture_output=True, text=True, timeout=90)
    score = oracle.evaluate(
        output / source_forecast.name, output / saved_forecast.name,
        output / source_order.name, output / saved_order.name,
    )
    assert score["joint_success"] and score["protection_success"]
