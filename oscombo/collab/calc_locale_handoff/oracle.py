"""Independent semantic scorer for CALC-LOCALE1 candidate-0.1 artifacts."""
from __future__ import annotations

import math
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from oscombo.collab.data_to_deck.fixtures import NS
from oscombo.collab.data_to_deck.oracle import read_ods

from . import CASE_ID, CASE_VERSION
from . import spec


def _tag(prefix: str, name: str) -> str:
    return f"{{{NS[prefix]}}}{name}"


def _column(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _normalize_formula(value: str) -> str:
    return (value.casefold().strip().replace("of:=", "=").replace("$", "")
            .replace("[", "").replace("]", "").replace(";", ",")
            .replace(" ", ""))


def _formula_cell_refs(value: str) -> set[str]:
    formula = _normalize_formula(value)
    return set(re.findall(r"(?<![a-z0-9])c\$?(\d+)(?!\d)", formula))


def _formulas(path: Path) -> dict[tuple[str, str], str]:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("content.xml"))
    found: dict[tuple[str, str], str] = {}
    for table in root.findall(f".//{_tag('table', 'table')}"):
        sheet = table.get(_tag("table", "name"), "")
        row_no = 0
        for row in table.iter(_tag("table", "table-row")):
            row_repeat = int(row.get(_tag("table", "number-rows-repeated"), "1"))
            col_no = 0
            for cell in list(row):
                if cell.tag not in (_tag("table", "table-cell"), _tag("table", "covered-table-cell")):
                    continue
                col_repeat = int(cell.get(_tag("table", "number-columns-repeated"), "1"))
                formula = cell.get(_tag("table", "formula"))
                if formula:
                    for dr in range(row_repeat):
                        for dc in range(col_repeat):
                            coord = f"{_column(col_no + dc + 1)}{row_no + dr + 1}"
                            found[(sheet, coord)] = _normalize_formula(formula)
                col_no += col_repeat
            row_no += row_repeat
    return found


def _load(path: Path) -> tuple[dict[str, list[list[object]]], dict[tuple[str, str], str]]:
    with zipfile.ZipFile(path) as archive:
        if archive.read("mimetype").decode("ascii") != "application/vnd.oasis.opendocument.spreadsheet":
            raise ValueError(f"not an ODS spreadsheet: {path}")
    return read_ods(path), _formulas(path)


def _cell(sheets: dict[str, list[list[object]]], sheet: str, row: int, col: int) -> object:
    try:
        return sheets[sheet][row - 1][col - 1]
    except (KeyError, IndexError):
        return None


def _equal(actual: object, expected: object) -> bool:
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return isinstance(actual, (int, float)) and not isinstance(actual, bool) and math.isclose(
            float(actual), float(expected), rel_tol=1e-9, abs_tol=1e-9)
    return actual == expected


def evaluate(workspace: str | Path, public_root: str | Path,
             gold_root: str | Path) -> dict[str, object]:
    """Score saved artifacts against separate public inputs and private Gold."""
    root, public, gold = Path(workspace), Path(public_root), Path(gold_root)
    result: dict[str, object] = {"case_id": CASE_ID, "case_version": CASE_VERSION,
                                 "actors": {}, "checks": {}, "joint_success": False}
    checks: dict[str, bool] = result["checks"]  # type: ignore[assignment]
    actual: dict[str, tuple[dict[str, list[list[object]]], dict[tuple[str, str], str]]] = {}
    gold_values: dict[str, tuple[dict[str, list[list[object]]], dict[tuple[str, str], str]]] = {}
    public_values: dict[str, dict[str, list[list[object]]]] = {}

    for filename in spec.PUBLIC_FILES:
        try:
            actual[filename] = _load(root / filename)
            checks[f"valid_ods:{filename}"] = True
        except (OSError, ValueError, KeyError, zipfile.BadZipFile, ET.ParseError):
            checks[f"valid_ods:{filename}"] = False
        try:
            gold_values[filename] = _load(gold / filename)
            checks[f"evaluator_gold_available:{filename}"] = True
        except (OSError, ValueError, KeyError, zipfile.BadZipFile, ET.ParseError):
            checks[f"evaluator_gold_available:{filename}"] = False
        try:
            public_values[filename] = read_ods(public / filename)
            checks[f"public_fixture_available:{filename}"] = True
        except (OSError, ValueError, KeyError, zipfile.BadZipFile, ET.ParseError):
            checks[f"public_fixture_available:{filename}"] = False

    expected_cells = {
        "vendor_us.ods": {"C2": ("Quote", 2, 3), "C3": ("Quote", 3, 3),
                          "C5": ("Quote", 5, 3)},
        "vendor_eu.ods": {"C2": ("Quote", 2, 3), "C3": ("Quote", 3, 3),
                          "C6": ("Quote", 6, 3)},
        "purchase_decision.ods": {"B2": ("Decision", 2, 2), "B3": ("Decision", 3, 2),
                                  "B4": ("Decision", 4, 2), "B5": ("Decision", 5, 2)},
    }
    for filename, coordinates in expected_cells.items():
        if filename not in actual or filename not in gold_values:
            for coord in coordinates:
                checks[f"gold:{filename}:{coord}"] = False
            continue
        actual_sheets, _ = actual[filename]
        expected_sheets, _ = gold_values[filename]
        for coord, (sheet, row, col) in coordinates.items():
            expected = _cell(expected_sheets, sheet, row, col)
            checks[f"gold:{filename}:{coord}"] = (
                expected is not None and _equal(_cell(actual_sheets, sheet, row, col), expected))

    expected_refs = {"vendor_us.ods": {"2", "3", "4"},
                     "vendor_eu.ods": {"2", "3", "4", "5"}}
    for filename, key in (("vendor_us.ods", ("Quote", "C5")),
                          ("vendor_eu.ods", ("Quote", "C6"))):
        if filename not in actual or filename not in gold_values:
            checks[f"formula:{filename}"] = False
            continue
        actual_formulas = actual[filename][1]
        gold_formulas = gold_values[filename][1]
        expected_formula = gold_formulas.get(key)
        actual_formula = actual_formulas.get(key)
        checks[f"formula:{filename}"] = (
            expected_formula is not None and actual_formula is not None
            and _formula_cell_refs(actual_formula) == expected_refs[filename])

    # Source cells are checked against the supplied public fixture, not against
    # actor-entered Evidence text or a claimed file revision.
    source_cells = {
        ("vendor_us.ods", "Quote", 2, 2), ("vendor_us.ods", "Quote", 3, 2),
        ("vendor_us.ods", "Quote", 4, 2), ("vendor_eu.ods", "Quote", 2, 2),
        ("vendor_eu.ods", "Quote", 3, 2), ("vendor_eu.ods", "Quote", 4, 2),
        ("vendor_eu.ods", "Quote", 5, 2), ("purchase_decision.ods", "Decision", 4, 2),
    }
    for filename, sheet, row, col in sorted(source_cells):
        original = _cell(public_values.get(filename, {}), sheet, row, col)
        changed = _cell(actual.get(filename, ({}, {}))[0], sheet, row, col)
        checks[f"source_preserved:{filename}:{sheet}:{row}:{col}"] = (
            filename in public_values and filename in actual and original is not None
            and _equal(changed, original))

    us_total = _cell(actual.get("vendor_us.ods", ({}, {}))[0], "Quote", 5, 3)
    eu_total = _cell(actual.get("vendor_eu.ods", ({}, {}))[0], "Quote", 6, 3)
    decision_sheets = actual.get("purchase_decision.ods", ({}, {}))[0]
    decision_us = _cell(decision_sheets, "Decision", 2, 2)
    decision_eu = _cell(decision_sheets, "Decision", 3, 2)
    cap = _cell(public_values.get("purchase_decision.ods", {}), "Decision", 4, 2)
    recommendation = _cell(decision_sheets, "Decision", 5, 2)
    if isinstance(us_total, (int, float)) and isinstance(eu_total, (int, float)) \
            and isinstance(cap, (int, float)):
        eligible = [(amount, name) for amount, name in ((us_total, "Northstar"),
                                                        (eu_total, "Elbe Office Supplies"))
                    if amount <= cap]
        expected_recommendation = min(eligible)[1] if eligible else "No eligible bid"
    else:
        expected_recommendation = None
    checks["A_used_B_saved_EU_total"] = _equal(decision_eu, eu_total)
    checks["A_used_own_saved_US_total"] = _equal(decision_us, us_total)
    checks["recommended_supplier_under_cap"] = (
        expected_recommendation is not None and recommendation == expected_recommendation)

    actor_a_prefixes = ("valid_ods:vendor_us", "valid_ods:purchase_decision", "gold:vendor_us",
                        "gold:purchase_decision", "formula:vendor_us", "source_preserved:vendor_us",
                        "source_preserved:purchase_decision", "A_used_", "recommended_supplier")
    actor_b_prefixes = ("valid_ods:vendor_eu", "gold:vendor_eu", "formula:vendor_eu",
                        "source_preserved:vendor_eu")
    actor_a_keys = [key for key in checks if key.startswith(actor_a_prefixes)]
    actor_b_keys = [key for key in checks if key.startswith(actor_b_prefixes)]
    result["actors"] = {
        "A": {"success": bool(actor_a_keys) and all(checks[key] for key in actor_a_keys),
              "checks": actor_a_keys},
        "B": {"success": bool(actor_b_keys) and all(checks[key] for key in actor_b_keys),
              "checks": actor_b_keys},
    }
    result["joint_success"] = bool(checks) and all(checks.values())
    result["gold_visibility"] = "evaluator-only; Actor workspaces must not mount this path"
    result["inference_boundary"] = (
        "semantic artifact score only; collaboration, desktop-state exposure, recovery, and causal attribution "
        "must be established from independent GUI, message, save-revision, and screenshot traces")
    result["errors"] = [name for name, passed in checks.items() if not passed]
    return result


def evaluate_controls(root: str | Path) -> dict[str, object]:
    """Score Gold and two deliberate negative ODS controls off-Guest."""
    base = Path(root)
    public = base / "public"
    gold = base / "private" / "gold"
    positive = evaluate(gold, public, gold)
    wrong_total = evaluate(base / "private" / "negative_wrong_eu_total", public, gold)
    text_parse = evaluate(base / "private" / "negative_text_parse", public, gold)
    return {
        "positive_joint_success": positive["joint_success"],
        "positive_errors": positive["errors"],
        "wrong_total_negative_joint_success": wrong_total["joint_success"],
        "wrong_total_negative_errors": wrong_total["errors"],
        "text_parse_negative_joint_success": text_parse["joint_success"],
        "text_parse_negative_errors": text_parse["errors"],
        "controls_pass": positive["joint_success"] is True
        and wrong_total["joint_success"] is False and text_parse["joint_success"] is False,
    }
