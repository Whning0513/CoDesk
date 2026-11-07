"""Deterministic public input and evaluator-only control ODS files."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from oscombo.collab.data_to_deck.fixtures import NS, _manifest_xml, _ods, _write_odf

from . import CASE_ID, CASE_VERSION
from . import spec


class FormulaValue:
    def __init__(self, formula: str, value: float):
        self.formula = formula
        self.value = value


def _cell(value: object) -> str:
    if isinstance(value, FormulaValue):
        formula = escape(value.formula, {'"': "&quot;"})
        shown = format(value.value, ".15g")
        return (f'<table:table-cell office:value-type="float" office:value="{shown}" '
                f'table:formula="{formula}"><text:p>{shown}</text:p></table:table-cell>')
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        shown = format(value, ".15g")
        return (f'<table:table-cell office:value-type="float" office:value="{shown}">'
                f'<text:p>{shown}</text:p></table:table-cell>')
    return (f'<table:table-cell office:value-type="string"><text:p>{escape(str(value))}'
            '</text:p></table:table-cell>')


def _write_workbook(path: Path, sheets: dict[str, list[list[object]]]) -> None:
    tables = []
    for name, rows in sheets.items():
        row_xml = "".join("<table:table-row>" + "".join(_cell(value) for value in row)
                          + "</table:table-row>" for row in rows)
        tables.append(f'<table:table table:name="{escape(name)}">{row_xml}</table:table>')
    mimetype = "application/vnd.oasis.opendocument.spreadsheet"
    content = (f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="{NS['office']}" xmlns:table="{NS['table']}"
 xmlns:text="{NS['text']}" xmlns:of="urn:oasis:names:tc:opendocument:xmlns:of:1.2"
 office:version="1.2"><office:body><office:spreadsheet>{''.join(tables)}
 </office:spreadsheet></office:body></office:document-content>''').encode()
    common = (f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles xmlns:office="{NS['office']}" xmlns:style="{NS['style']}"
 office:version="1.2"><office:styles/></office:document-styles>''').encode()
    _write_odf(path, mimetype, {
        "content.xml": content, "styles.xml": common,
        "meta.xml": (f'''<?xml version="1.0"?><office:document-meta xmlns:office="{NS['office']}"
 office:version="1.2"><office:meta/></office:document-meta>''').encode(),
        "settings.xml": (f'''<?xml version="1.0"?><office:document-settings xmlns:office="{NS['office']}"
 office:version="1.2"><office:settings/></office:document-settings>''').encode(),
        "META-INF/manifest.xml": _manifest_xml(mimetype, "content.xml"),
    })


def public_sheets() -> dict[str, dict[str, list[list[object]]]]:
    return {
        "vendor_us.ods": {"Quote": [
            ["Field", "Source quote", "Entered value", "Notes"],
            ["Unit price USD", "$24.80", "", "Enter as a number"],
            ["Shipping USD", "$18.00", "", "Enter as a number"],
            ["Quantity", 10, 10, "Units"],
            ["Landed total USD", "", "", "Unit price × quantity + shipping"],
            ["Evidence", "Northstar quote", "", "Preserve source values"],
        ]},
        "vendor_eu.ods": {"Quote": [
            ["Field", "Source quote", "Entered value", "Notes"],
            ["Unit price EUR", "€19,50", "", "Enter as a number"],
            ["Freight EUR", "€24,00", "", "Enter as a number"],
            ["Quantity", 10, 10, "Units"],
            ["USD per EUR", 1.08, 1.08, "Use the supplied rate"],
            ["Landed total USD", "", "", "(unit price × quantity + freight) × rate"],
            ["Evidence", "Elbe Office Supplies quote", "", "Preserve source values"],
        ]},
        "purchase_decision.ods": {"Decision": [
            ["Metric", "Value", "Evidence"],
            ["Northstar landed USD", "", "Saved vendor_us.ods"],
            ["Elbe landed USD", "", "Saved vendor_eu.ods"],
            ["Budget cap USD", 250, "Visible task cap"],
            ["Recommended supplier", "", "Compare both saved totals and the cap"],
            ["Source note", "", "Identify the saved quote revision actually used"],
        ]},
    }


def gold_sheets() -> dict[str, dict[str, list[list[object]]]]:
    us = public_sheets()["vendor_us.ods"]["Quote"]
    us[1][2] = 24.8
    us[2][2] = 18.0
    us[4][2] = FormulaValue("of:=[.C2]*[.C4]+[.C3]", 266.0)
    us[5][2] = "Northstar source quote; USD"
    eu = public_sheets()["vendor_eu.ods"]["Quote"]
    eu[1][2] = 19.5
    eu[2][2] = 24.0
    eu[5][2] = FormulaValue("of:=([.C2]*[.C4]+[.C3])*[.C5]", 236.52)
    eu[6][2] = "Elbe source quote; EUR converted at supplied rate"
    decision = public_sheets()["purchase_decision.ods"]["Decision"]
    decision[1][1] = 266.0
    decision[2][1] = 236.52
    decision[4][1] = "Elbe Office Supplies"
    decision[5][1] = "vendor_eu.ods saved quote used"
    return {"vendor_us.ods": {"Quote": us},
            "vendor_eu.ods": {"Quote": eu},
            "purchase_decision.ods": {"Decision": decision}}


def negative_sheets() -> dict[str, dict[str, list[list[object]]]]:
    result = gold_sheets()
    result["vendor_eu.ods"]["Quote"][5][2] = FormulaValue(
        "of:=([.C2]*[.C4]+[.C3])*[.C5]", 2365.2)
    result["purchase_decision.ods"]["Decision"][2][1] = 2365.2
    result["purchase_decision.ods"]["Decision"][4][1] = "Northstar"
    return result


def negative_text_parse_sheets() -> dict[str, dict[str, list[list[object]]]]:
    result = gold_sheets()
    result["vendor_eu.ods"]["Quote"][1][2] = "19.50"
    result["vendor_eu.ods"]["Quote"][5][2] = "#VALUE!"
    result["purchase_decision.ods"]["Decision"][2][1] = "#VALUE!"
    result["purchase_decision.ods"]["Decision"][4][1] = ""
    return result


def _write_set(root: Path, files: dict[str, dict[str, list[list[object]]]]) -> dict[str, dict[str, Any]]:
    hashes = {}
    for filename, sheets in files.items():
        path = root / filename
        _write_workbook(path, sheets)
        data = path.read_bytes()
        hashes[filename] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    return hashes


def build_fixture(output: str | Path) -> dict[str, Any]:
    """Create public inputs and private scoring controls in a new empty root."""
    root = Path(output)
    if root.exists() and (root.is_symlink() or any(root.iterdir())):
        raise FileExistsError(f"fixture output must be a new/empty owned directory: {root}")
    root.mkdir(parents=True, exist_ok=True)
    public_hashes = _write_set(root / "public", public_sheets())
    gold_hashes = _write_set(root / "private" / "gold", gold_sheets())
    negative_hashes = _write_set(root / "private" / "negative_wrong_eu_total", negative_sheets())
    text_negative_hashes = _write_set(root / "private" / "negative_text_parse", negative_text_parse_sheets())
    manifest = {
        "schema_version": 1,
        "case_id": CASE_ID,
        "case_version": CASE_VERSION,
        "fixture_id": "CALC-LOCALE1-QUOTE-001",
        "files": public_hashes,
        "actor_visible_paths": list(spec.PUBLIC_FILES),
    }
    (root / "public" / "fixture_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (root / "private" / "fixture_manifest.json").write_text(
        json.dumps({"gold_sha256": gold_hashes, "gold_visibility": "evaluator only",
                    "negative_wrong_total_sha256": negative_hashes,
                    "negative_text_parse_sha256": text_negative_hashes},
                   ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def copy_public_fixture(destination: str | Path) -> dict[str, Any]:
    dest = Path(destination)
    if dest.exists() and (dest.is_symlink() or any(dest.iterdir())):
        raise FileExistsError(f"destination must be new or empty: {dest}")
    dest.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).parent / "fixtures" / "public"
    for filename in spec.PUBLIC_FILES + ("fixture_manifest.json",):
        shutil.copy2(source / filename, dest / filename)
    return json.loads((dest / "fixture_manifest.json").read_text(encoding="utf-8"))
