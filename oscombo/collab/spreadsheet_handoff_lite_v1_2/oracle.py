"""Evaluator-only checks for values, general cost formula, and source protection."""
from __future__ import annotations

import ast
import math
import re
import zipfile
from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree as ET

from oscombo.collab.data_to_deck.fixtures import NS
from oscombo.collab.spreadsheet_handoff_lite_v1_1.oracle import _at, _number, _ods_rows, _source_equal
from . import spec
from .fixtures import forecast_rows, order_rows


def _formula_at(path: str | Path, sheet: str, row_num: int, col_num: int) -> str | None:
    q = lambda ns, name: f"{{{NS[ns]}}}{name}"
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("content.xml"))
    table = next((x for x in root.findall(f".//{q('table','table')}")
                  if x.get(q("table", "name")) == sheet), None)
    if table is None:
        return None
    row_index = 0
    for row in table.iter(q("table", "table-row")):
        count = int(row.get(q("table", "number-rows-repeated"), "1"))
        if count < 1:
            raise ValueError("invalid row repetition")
        if row_index < row_num <= row_index + count:
            col_index = 0
            for cell in list(row):
                if cell.tag not in (q("table", "table-cell"), q("table", "covered-table-cell")):
                    continue
                count_col = int(cell.get(q("table", "number-columns-repeated"), "1"))
                if count_col < 1:
                    raise ValueError("invalid cell repetition")
                if col_index < col_num <= col_index + count_col:
                    return cell.get(q("table", "formula"))
                col_index += count_col
            return None
        row_index += count
    return None


def _general_cost_formula(formula: str | None) -> bool:
    """Accept algebraic E3*C3 formulas without evaluating arbitrary code."""
    if not isinstance(formula, str) or len(formula) > 200:
        return False
    expression = re.sub(r"^(?:of:|oooc:)?=", "", formula.strip(), flags=re.I)
    expression = re.sub(r"\[\.\$?([EC])\$?3\]", lambda m: m.group(1).upper() + "3", expression, flags=re.I)
    expression = expression.replace("$", "").replace(";", ",")
    if "[" in expression or "]" in expression or "." in expression:
        return False
    try:
        tree = ast.parse(expression.upper(), mode="eval")
        if sum(1 for _ in ast.walk(tree)) > 40:
            return False

        def add(a, b, sign=1):
            out = dict(a)
            for k, v in b.items():
                out[k] = out.get(k, Fraction(0)) + sign * v
            return {k: v for k, v in out.items() if v}

        def mul(a, b):
            out = {}
            for (x, y), v in a.items():
                for (u, w), z in b.items():
                    key = (x + u, y + w)
                    if sum(key) > 4:
                        raise ValueError("formula degree")
                    out[key] = out.get(key, Fraction(0)) + v * z
            return {k: v for k, v in out.items() if v}

        def poly(node):
            if isinstance(node, ast.Name) and node.id in {"E3", "C3"}:
                return {(1, 0) if node.id == "E3" else (0, 1): Fraction(1)}
            if isinstance(node, ast.Constant) and type(node.value) is int and abs(node.value) <= 1000:
                return {(0, 0): Fraction(node.value)} if node.value else {}
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                value = poly(node.operand)
                return value if isinstance(node.op, ast.UAdd) else {k: -v for k, v in value.items()}
            if isinstance(node, ast.BinOp):
                a, b = poly(node.left), poly(node.right)
                if isinstance(node.op, ast.Add): return add(a, b)
                if isinstance(node.op, ast.Sub): return add(a, b, -1)
                if isinstance(node.op, ast.Mult): return mul(a, b)
                if isinstance(node.op, ast.Div) and set(b) == {(0, 0)} and b[(0, 0)] != 0:
                    return {k: v / b[(0, 0)] for k, v in a.items()}
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords and node.args:
                if node.func.id == "PRODUCT":
                    out = {(0, 0): Fraction(1)}
                    for arg in node.args: out = mul(out, poly(arg))
                    return out
                if node.func.id == "SUM":
                    out = {}
                    for arg in node.args: out = add(out, poly(arg))
                    return out
            raise ValueError("unsupported formula")
        return poly(tree.body) == {(1, 1): Fraction(1)}
    except (ValueError, SyntaxError, ZeroDivisionError, RecursionError, OverflowError):
        return False


def evaluate(source_forecast: str | Path, saved_forecast: str | Path,
             source_order: str | Path, saved_order: str | Path) -> dict:
    try:
        input_forecast = _ods_rows(source_forecast, "Forecast")
        analysis = _ods_rows(saved_forecast, "Forecast")
        input_order = _ods_rows(source_order, "Order")
        plan = _ods_rows(saved_order, "Order")
        cost_formula = _formula_at(saved_order, "Order", 3, 6)
    except (zipfile.BadZipFile, ET.ParseError, ValueError, KeyError, UnicodeDecodeError) as exc:
        return {"case_id": spec.CASE_ID, "case_version": spec.CASE_VERSION,
                "actors": {r: {"success": False, "checks": {}} for r in "AB"},
                "joint_success": False, "protection_success": False,
                "invalid_artifact": type(exc).__name__}
    public_forecast, public_order = forecast_rows(), order_rows()
    fixed_forecast = tuple(range(7)) + (8,)
    input_intact = (_source_equal(input_forecast, public_forecast, fixed_forecast)
                    and _source_equal(input_order, public_order, (0, 1, 2, 3, 6)))
    forecast_intact = _source_equal(analysis, public_forecast, fixed_forecast)
    order_intact = _source_equal(plan, public_order, (0, 1, 2, 3, 6))
    f, o = public_forecast[2], public_order[2]
    need = max(0, sum(f[1:4]) / 3 * 2 + f[6] - f[4] - f[5])
    a_need, units, cost = (_number(_at(analysis[2], 7)), _number(_at(plan[2], 4)),
                           _number(_at(plan[2], 5)))
    expected_units = math.ceil(need / o[1]) * o[1]
    a_checks = {"input_fixture_intact": input_intact, "forecast_source_intact": forecast_intact,
                "correct_nonnegative_net_need": a_need is not None and math.isclose(a_need, need, abs_tol=1e-9)}
    a_success = all(a_checks.values())
    expected_for_saved = (math.ceil(a_need / o[1]) * o[1]
                          if a_need is not None and a_need >= 0 else None)
    local_order_correct = (units is not None and expected_for_saved is not None
                           and math.isclose(units, expected_for_saved, abs_tol=1e-9))
    global_order_correct = units is not None and math.isclose(units, expected_units, abs_tol=1e-9)
    b_checks = {"order_source_intact": order_intact,
                "correct_whole_case_order": local_order_correct,
                "general_cost_formula": _general_cost_formula(cost_formula),
                "correct_purchase_cost": cost is not None and units is not None and math.isclose(cost, units * o[2], abs_tol=1e-9),
                "within_budget_cap": cost is not None and cost <= o[3],
                "matches_saved_forecast": local_order_correct}
    b_success = all(b_checks.values())
    return {"case_id": spec.CASE_ID, "case_version": spec.CASE_VERSION,
            "actors": {"A": {"success": a_success, "checks": a_checks},
                       "B": {"success": b_success, "local_success": b_success, "checks": b_checks,
                             "global_checks": {"correct_whole_case_order_for_true_need": global_order_correct},
                             "global_success": b_success and global_order_correct}},
            "joint_success": a_success and b_success and global_order_correct,
            "protection_success": input_intact and forecast_intact and order_intact,
            "expected_need_evaluator_only": need,
            "measured": {"saved_forecast_need": a_need, "order_units": units,
                         "order_cost_usd": cost, "order_cost_formula": cost_formula},
            "behavioral_handoff": "audit saved revision mirror, GUI view screenshot, messages and edit chronology separately"}
