"""Evaluator-only artifact checks; peer behavior is audited from the trace."""
from __future__ import annotations

import math
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from oscombo.collab.data_to_deck.oracle import read_ods, _content_equal
from . import spec
from .fixtures import forecast_rows, order_rows

ODS_MIME = "application/vnd.oasis.opendocument.spreadsheet"


def _ods_rows(path: str | Path, sheet: str) -> list[list[object]]:
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None or archive.read("mimetype").decode() != ODS_MIME:
            raise ValueError("invalid ODS workbook")
    sheets = read_ods(path)
    if set(sheets) != {sheet} or len(sheets[sheet]) != 3:
        raise ValueError("unexpected sheet or row set")
    return sheets[sheet]


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, str) and re.fullmatch(r"\s*\d+(?:\.\d+)?\s*", value):
        result = float(value)
    else:
        return None
    return result if math.isfinite(result) else None


def _at(row: list[object], index: int) -> object:
    return row[index] if len(row) > index else ""


def _source_equal(actual: list[list[object]], expected: list[list[object]],
                  fixed_columns: tuple[int, ...]) -> bool:
    return (len(actual) == 3 and all(_content_equal(actual[i], expected[i]) for i in (0, 1))
            and all(_content_equal(_at(actual[2], i), expected[2][i]) for i in fixed_columns))


def evaluate(source_forecast: str | Path, saved_forecast: str | Path,
             source_order: str | Path, saved_order: str | Path) -> dict:
    try:
        input_forecast = _ods_rows(source_forecast, "Forecast")
        analysis = _ods_rows(saved_forecast, "Forecast")
        input_order = _ods_rows(source_order, "Order")
        plan = _ods_rows(saved_order, "Order")
    except (OSError, zipfile.BadZipFile, ET.ParseError, ValueError, KeyError, UnicodeDecodeError) as exc:
        return {"case_id": spec.CASE_ID, "case_version": spec.CASE_VERSION,
                "actors": {r: {"success": False, "checks": {}} for r in "AB"},
                "joint_success": False, "protection_success": False,
                "invalid_artifact": type(exc).__name__}

    public_forecast, public_order = forecast_rows(), order_rows()
    input_intact = (_source_equal(input_forecast, public_forecast, tuple(range(7)))
                    and _source_equal(input_order, public_order, (0, 1, 2, 3, 6)))
    forecast_source_intact = _source_equal(analysis, public_forecast, tuple(range(7)))
    order_source_intact = _source_equal(plan, public_order, (0, 1, 2, 3, 6))
    f = public_forecast[2]
    raw_need = sum(f[1:4]) / 3 * 2 + f[6] - f[4] - f[5]
    need = max(0, raw_need)
    a_need = _number(_at(analysis[2], 7))
    evidence = _at(analysis[2], 8)
    checks_a = {
        "input_fixture_intact": input_intact,
        "forecast_source_intact": forecast_source_intact,
        "correct_nonnegative_net_need": a_need is not None and math.isclose(a_need, need, abs_tol=1e-9),
        "evidence_covers_sales_and_inventory": isinstance(evidence, str) and bool(
            re.search(r"(?<![A-Za-z])B3\s*:\s*G3\b", evidence, re.I)
            or all(re.search(rf"(?<![A-Za-z]){column}3\b", evidence, re.I)
                   for column in "BCDEFG")),
    }
    a_success = all(checks_a.values())
    o = public_order[2]
    expected_units = math.ceil(need / o[1]) * o[1]
    expected_cost = expected_units * o[2]
    units = _number(_at(plan[2], 4))
    cost = _number(_at(plan[2], 5))
    checks_b = {
        "order_source_intact": order_source_intact,
        "correct_whole_case_order": units is not None and math.isclose(units, expected_units, abs_tol=1e-9),
        "correct_purchase_cost": cost is not None and math.isclose(cost, expected_cost, abs_tol=1e-9),
        "within_budget_cap": cost is not None and cost <= o[3],
        "matches_saved_forecast": a_success and units is not None and
            math.isclose(units, math.ceil(a_need / o[1]) * o[1], abs_tol=1e-9),
    }
    b_success = all(checks_b.values())
    return {"case_id": spec.CASE_ID, "case_version": spec.CASE_VERSION,
            "actors": {"A": {"success": a_success, "checks": checks_a},
                       "B": {"success": b_success, "checks": checks_b}},
            "joint_success": a_success and b_success,
            "protection_success": input_intact and forecast_source_intact and order_source_intact,
            "expected_need_evaluator_only": need,
            "behavioral_handoff": "audit A revision/message and B read/edit/save chronology separately"}
