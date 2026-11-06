"""Evaluator-only scoring for Spreadsheet Handoff Lite v1.3."""
from __future__ import annotations

import ast
import math
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from oscombo.collab.data_to_deck.fixtures import NS
from oscombo.collab.data_to_deck.oracle import read_ods, _content_equal
from . import spec
from .fixtures import (forecast_rows, order_rows, B_UNITS_FORMULA, B_COST_FORMULA)

ODS_MIME = "application/vnd.oasis.opendocument.spreadsheet"


def _q(prefix: str, local: str) -> str:
    return f"{{{NS[prefix]}}}{local}"


def _rows(path: str | Path, sheet: str) -> list[list[object]]:
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None or archive.read("mimetype").decode() != ODS_MIME:
            raise ValueError("invalid ODS workbook")
    sheets = read_ods(path)
    if set(sheets) != {sheet} or len(sheets[sheet]) != 3:
        raise ValueError("unexpected ODS sheet or row count")
    return sheets[sheet]


def _formula_at(path: str | Path, sheet: str, row_num: int, col_num: int) -> str | None:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("content.xml"))
    table = next((x for x in root.findall(f".//{_q('table','table')}")
                  if x.get(_q("table", "name")) == sheet), None)
    if table is None:
        return None
    row_start = 1
    for row in table.findall(_q("table", "table-row")):
        row_repeat = int(row.get(_q("table", "number-rows-repeated"), "1"))
        if row_start <= row_num < row_start + row_repeat:
            col_start = 1
            for cell in row:
                if cell.tag not in (_q("table", "table-cell"), _q("table", "covered-table-cell")):
                    continue
                col_repeat = int(cell.get(_q("table", "number-columns-repeated"), "1"))
                if col_start <= col_num < col_start + col_repeat:
                    return cell.get(_q("table", "formula"))
                col_start += col_repeat
            return None
        row_start += row_repeat
    return None


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, str) and re.fullmatch(r"\s*-?\d+(?:\.\d+)?\s*", value):
        result = float(value)
    else:
        return None
    return result if math.isfinite(result) else None


def _at(row: list[object], index: int) -> object:
    return row[index] if len(row) > index else ""


def _source_equal(actual: list[list[object]], expected: list[list[object]],
                  fixed_columns: tuple[int, ...]) -> bool:
    return (len(actual) == 3
            and all(_content_equal(actual[i], expected[i]) for i in (0, 1))
            and all(_content_equal(_at(actual[2], i), expected[2][i]) for i in fixed_columns))


def _formula_tree(formula: str | None) -> ast.AST:
    if not isinstance(formula, str) or len(formula) > 300:
        raise ValueError("missing or oversized formula")
    expression = re.sub(r"^(?:of:|oooc:)?=", "", formula.strip(), flags=re.I)
    expression = re.sub(
        r"\[\.\$?([A-Za-z]{1,3})\$?(\d+)\]",
        lambda m: m.group(1).upper() + m.group(2), expression)
    expression = expression.replace("$", "").replace(";", ",")
    expression = re.sub(r"\bMAX\s*\(", "max(", expression, flags=re.I)
    if "[" in expression or "]" in expression or "!" in expression or ":" in expression:
        raise ValueError("unsupported cell reference")
    tree = ast.parse(expression, mode="eval")
    if sum(1 for _ in ast.walk(tree)) > 100:
        raise ValueError("formula is too complex")
    return tree


def _formula_eval(node: ast.AST, cells: dict[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return _formula_eval(node.body, cells)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return float(node.value)
    if isinstance(node, ast.Name) and node.id.upper() in cells:
        return float(cells[node.id.upper()])
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        val = _formula_eval(node.operand, cells)
        return val if isinstance(node.op, ast.UAdd) else -val
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        left, right = _formula_eval(node.left, cells), _formula_eval(node.right, cells)
        if isinstance(node.op, ast.Add): result = left + right
        elif isinstance(node.op, ast.Sub): result = left - right
        elif isinstance(node.op, ast.Mult): result = left * right
        else: result = left / right
        if not math.isfinite(result):
            raise ValueError("non-finite formula result")
        return result
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "max":
        if node.keywords or len(node.args) < 1:
            raise ValueError("unsupported max call")
        return max(_formula_eval(arg, cells) for arg in node.args)
    raise ValueError("unsupported formula operation")


def _formula_names(tree: ast.AST) -> set[str]:
    return {node.id.upper() for node in ast.walk(tree) if isinstance(node, ast.Name)
            and node.id.lower() != "max"}


def _formula_semantics(formula: str | None, values: dict[str, float],
                       expected: float, expected_sensitivity: dict[str, float]) -> bool:
    try:
        tree = _formula_tree(formula)
        if _formula_names(tree) != set(expected_sensitivity):
            return False
        if not math.isclose(_formula_eval(tree, values), expected, rel_tol=1e-9, abs_tol=1e-9):
            return False
        # Check every required input's local influence. This rejects constants
        # and formulas that mention a source cell only as a zero-weight decoy.
        for cell, slope in expected_sensitivity.items():
            changed = dict(values)
            changed[cell] += 1
            delta = _formula_eval(tree, changed) - _formula_eval(tree, values)
            if not math.isclose(delta, slope, rel_tol=1e-8, abs_tol=1e-8):
                return False
        return True
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError, RecursionError):
        return False


def evaluate(source_forecast: str | Path, saved_forecast: str | Path,
             source_order: str | Path, saved_order: str | Path) -> dict:
    try:
        public_f = _rows(source_forecast, "Forecast")
        analysis = _rows(saved_forecast, "Forecast")
        public_o = _rows(source_order, "Order")
        plan = _rows(saved_order, "Order")
        a_formula = _formula_at(saved_forecast, "Forecast", 3, 8)
        b_units_formula = _formula_at(saved_order, "Order", 3, 7)
        b_cost_formula = _formula_at(saved_order, "Order", 3, 8)
        public_a_formula = _formula_at(source_forecast, "Forecast", 3, 8)
        public_units_formula = _formula_at(source_order, "Order", 3, 7)
        public_cost_formula = _formula_at(source_order, "Order", 3, 8)
    except (zipfile.BadZipFile, ET.ParseError, ValueError, KeyError, UnicodeDecodeError) as exc:
        return {
            "case_id": spec.CASE_ID, "case_version": spec.CASE_VERSION,
            "actors": {role: {"success": False, "checks": {}} for role in "AB"},
            "joint_success": False, "protection_success": False,
            "invalid_artifact": type(exc).__name__,
        }

    expected_f, expected_o = forecast_rows(), order_rows()
    input_intact = (_source_equal(public_f, expected_f, tuple(range(7)))
                    and _source_equal(public_o, expected_o, (0, 1, 2, 3))
                    and _at(public_f[2], 7) == "" and public_a_formula is None
                    and _number(_at(public_o[2], 4)) == 0
                    and _number(_at(public_o[2], 5)) == 0
                    and _number(_at(public_o[2], 6)) == 0
                    and _number(_at(public_o[2], 7)) == 0
                    and public_units_formula == B_UNITS_FORMULA
                    and public_cost_formula == B_COST_FORMULA)
    forecast_intact = _source_equal(analysis, expected_f, tuple(range(7)))
    order_intact = _source_equal(plan, expected_o, (0, 1, 2, 3))
    base_f, base_o = expected_f[2], expected_o[2]
    source_cells = {letter + "3": float(base_f[i]) for i, letter in enumerate("BCDEFG", start=1)}
    need = max(0.0, (source_cells["B3"] + source_cells["C3"] + source_cells["D3"]) / 3 * 2
               + source_cells["G3"] - source_cells["E3"] - source_cells["F3"])
    a_need = _number(_at(analysis[2], 7))
    a_formula_ok = _formula_semantics(
        a_formula, source_cells, need,
        {"B3": 2 / 3, "C3": 2 / 3, "D3": 2 / 3, "E3": -1, "F3": -1, "G3": 1})
    a_checks = {
        "input_fixture_intact": input_intact,
        "forecast_source_intact": forecast_intact,
        "correct_nonnegative_net_need": a_need is not None and math.isclose(a_need, need, abs_tol=1e-9),
        "formula_uses_sales_stock_inbound_and_safety_inputs": a_formula_ok,
    }
    a_success = all(a_checks.values())

    pack, price, budget = float(base_o[1]), float(base_o[2]), float(base_o[3])
    entered_need = _number(_at(plan[2], 4))
    cartons = _number(_at(plan[2], 5))
    units = _number(_at(plan[2], 6))
    cost = _number(_at(plan[2], 7))
    expected_cartons_local = math.ceil(a_need / pack) if a_need is not None and a_need >= 0 else None
    expected_units_local = expected_cartons_local * pack if expected_cartons_local is not None else None
    expected_cost_local = expected_units_local * price if expected_units_local is not None else None
    units_formula_ok = _formula_semantics(
        b_units_formula, {"F3": cartons or 0.0, "B3": pack},
        expected_units_local if expected_units_local is not None else math.nan,
        {"F3": pack, "B3": cartons or 0.0})
    cost_formula_ok = _formula_semantics(
        b_cost_formula, {"G3": units or 0.0, "C3": price},
        expected_cost_local if expected_cost_local is not None else math.nan,
        {"G3": price, "C3": units or 0.0})
    b_checks = {
        "order_source_intact": order_intact,
        "need_transcribed_from_saved_forecast": entered_need is not None and a_need is not None
            and math.isclose(entered_need, a_need, abs_tol=1e-9),
        "correct_minimum_whole_carton_count": cartons is not None and expected_cartons_local is not None
            and math.isclose(cartons, expected_cartons_local, abs_tol=1e-9),
        "calculated_individual_units": units is not None and expected_units_local is not None
            and math.isclose(units, expected_units_local, abs_tol=1e-9) and units_formula_ok,
        "calculated_total_cost": cost is not None and expected_cost_local is not None
            and math.isclose(cost, expected_cost_local, abs_tol=1e-9) and cost_formula_ok,
        "within_budget_cap": cost is not None and cost <= budget,
    }
    b_success = all(b_checks.values())

    true_cartons = math.ceil(need / pack)
    global_units_ok = units is not None and math.isclose(units, true_cartons * pack, abs_tol=1e-9)
    global_cost_ok = cost is not None and math.isclose(cost, true_cartons * pack * price, abs_tol=1e-9)
    global_budget_ok = cost is not None and cost <= budget
    joint = a_success and b_success and global_units_ok and global_cost_ok and global_budget_ok
    return {
        "case_id": spec.CASE_ID, "case_version": spec.CASE_VERSION,
        "actors": {
            "A": {"success": a_success, "checks": a_checks},
            "B": {"success": b_success, "local_success": b_success, "checks": b_checks,
                  "global_checks": {"correct_cartons_for_true_need": cartons is not None
                                    and math.isclose(cartons, true_cartons, abs_tol=1e-9),
                                    "correct_units_for_true_need": global_units_ok,
                                    "correct_cost_for_true_need": global_cost_ok,
                                    "within_budget_for_true_need": global_budget_ok},
                  "global_success": b_success and global_units_ok and global_cost_ok and global_budget_ok},
        },
        "joint_success": joint,
        "protection_success": input_intact and forecast_intact and order_intact,
        "expected_need_evaluator_only": need,
        "measured": {"saved_forecast_need": a_need, "need_entered_in_order": entered_need,
                     "cartons": cartons, "order_units": units, "order_cost_usd": cost,
                     "forecast_formula": a_formula, "units_formula": b_units_formula,
                     "cost_formula": b_cost_formula},
        "behavioral_handoff": "verify revision/message and B GUI-read/edit/save chronology separately",
    }
