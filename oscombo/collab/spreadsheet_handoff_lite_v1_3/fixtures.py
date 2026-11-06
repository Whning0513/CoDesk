"""Versioned public Calc files for Case 6 Lite v1.3."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from oscombo.collab.data_to_deck.fixtures import NS, _ods
from . import spec

OF_NS = "urn:oasis:names:tc:opendocument:xmlns:of:1.2"
B_UNITS_FORMULA = "of:=[.F3]*[.B3]"
B_COST_FORMULA = "of:=[.G3]*[.C3]"


def forecast_rows() -> list[list[object]]:
    return [
        ["SKU-LAMP | two-month replenishment need (individual units)"],
        ["SKU", "Jun sales (units)", "Jul sales (units)", "Aug sales (units)",
         "On-hand (units)", "Inbound (units)", "Safety stock (units)", "NET NEED (units)"],
        ["SKU-LAMP", 40, 50, 60, 39, 18, 30],
    ]


def order_rows() -> list[list[object]]:
    return [
        ["SKU-LAMP | full-carton procurement decision"],
        ["SKU", "Units / carton", "USD / unit", "Budget USD",
         "Need (individual units)", "WHOLE CARTONS TO ORDER",
         "TOTAL INDIVIDUAL UNITS", "TOTAL COST USD"],
        ["SKU-LAMP", 10, 28, 2300, 0, 0, 0, 0],
    ]


def _q(prefix: str, local: str) -> str:
    return f"{{{NS[prefix]}}}{local}"


def _set_formula(path: Path, sheet: str, row_num: int, col_num: int, formula: str) -> None:
    with zipfile.ZipFile(path) as archive:
        members = [(info, archive.read(info.filename)) for info in archive.infolist()]
    content = next(data for info, data in members if info.filename == "content.xml")
    root = ET.fromstring(content)
    root.set("xmlns:of", OF_NS)
    table = next((item for item in root.findall(f".//{_q('table','table')}")
                  if item.get(_q("table", "name")) == sheet), None)
    if table is None:
        raise ValueError(f"missing sheet {sheet!r}")
    rows = table.findall(_q("table", "table-row"))
    if not 1 <= row_num <= len(rows):
        raise ValueError(f"missing row {row_num}")
    cells = rows[row_num - 1].findall(_q("table", "table-cell"))
    if not 1 <= col_num <= len(cells):
        raise ValueError(f"missing cell column {col_num}")
    cells[col_num - 1].set(_q("table", "formula"), formula)
    updated = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(path, "w") as archive:
        for info, data in members:
            archive.writestr(info, updated if info.filename == "content.xml" else data)


def _set_layout(path: Path, sheet_name: str, column: int) -> None:
    """Set a legible starting view and place the cursor at the first task cell."""
    for prefix in ("office", "table", "text", "style", "fo"):
        ET.register_namespace(prefix, NS[prefix])
    with zipfile.ZipFile(path) as archive:
        members = [(info, archive.read(info.filename)) for info in archive.infolist()]
    content = next(data for info, data in members if info.filename == "content.xml")
    root = ET.fromstring(content)
    styles = ET.Element(_q("office", "automatic-styles"))
    col_style = ET.SubElement(
        styles, _q("style", "style"),
        {_q("style", "name"): "wide-v13", _q("style", "family"): "table-column"})
    ET.SubElement(col_style, _q("style", "table-column-properties"),
                  {_q("style", "column-width"): "2.4cm"})
    row_style = ET.SubElement(
        styles, _q("style", "style"),
        {_q("style", "name"): "tall-v13", _q("style", "family"): "table-row"})
    ET.SubElement(row_style, _q("style", "table-row-properties"),
                  {_q("style", "row-height"): "0.9cm"})
    cell_style = ET.SubElement(
        styles, _q("style", "style"),
        {_q("style", "name"): "legible-v13", _q("style", "family"): "table-cell"})
    ET.SubElement(cell_style, _q("style", "text-properties"), {_q("fo", "font-size"): "12pt"})
    root.insert(0, styles)
    for table in root.findall(f".//{_q('table','table')}"):
        table.insert(0, ET.Element(_q("table", "table-column"), {
            _q("table", "style-name"): "wide-v13",
            _q("table", "number-columns-repeated"): "8",
            _q("table", "default-cell-style-name"): "legible-v13"}))
        for row in table.findall(_q("table", "table-row")):
            row.set(_q("table", "style-name"), "tall-v13")
    updated = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    settings = f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-settings xmlns:office="{NS['office']}" xmlns:config="urn:oasis:names:tc:opendocument:xmlns:config:1.0" xmlns:ooo="http://openoffice.org/2004/office" office:version="1.2">
 <office:settings><config:config-item-set config:name="ooo:view-settings">
  <config:config-item-map-indexed config:name="Views"><config:config-item-map-entry>
   <config:config-item config:name="ViewId" config:type="string">view1</config:config-item>
   <config:config-item-map-named config:name="Tables"><config:config-item-map-entry config:name="{sheet_name}">
    <config:config-item config:name="CursorPositionX" config:type="int">{column}</config:config-item>
    <config:config-item config:name="CursorPositionY" config:type="int">2</config:config-item>
    <config:config-item config:name="ActiveSplitRange" config:type="short">2</config:config-item>
    <config:config-item config:name="PositionLeft" config:type="int">0</config:config-item>
    <config:config-item config:name="PositionRight" config:type="int">0</config:config-item>
    <config:config-item config:name="PositionTop" config:type="int">0</config:config-item>
    <config:config-item config:name="PositionBottom" config:type="int">0</config:config-item>
    <config:config-item config:name="ZoomType" config:type="short">0</config:config-item>
    <config:config-item config:name="ZoomValue" config:type="int">100</config:config-item>
    <config:config-item config:name="PageViewZoomValue" config:type="int">60</config:config-item>
    <config:config-item config:name="ShowGrid" config:type="boolean">true</config:config-item>
   </config:config-item-map-entry></config:config-item-map-named>
   <config:config-item config:name="ActiveTable" config:type="string">{sheet_name}</config:config-item>
   <config:config-item config:name="ZoomType" config:type="short">0</config:config-item>
   <config:config-item config:name="ZoomValue" config:type="int">100</config:config-item>
  </config:config-item-map-entry></config:config-item-map-indexed>
 </config:config-item-set></office:settings></office:document-settings>'''.encode()
    with zipfile.ZipFile(path, "w") as archive:
        for info, data in members:
            payload = updated if info.filename == "content.xml" else settings if info.filename == "settings.xml" else data
            archive.writestr(info, payload)


def build_fixture(root: str | Path) -> dict:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise FileExistsError(f"Lite v1.3 fixture destination is not empty: {root}")
    forecast = root / spec.FIXTURE_NAMES["forecast"]
    order = root / spec.FIXTURE_NAMES["order"]
    _ods(forecast, {"Forecast": forecast_rows()})
    _ods(order, {"Order": order_rows()})
    _set_layout(forecast, "Forecast", 7)  # H3
    _set_layout(order, "Order", 4)         # E3
    _set_formula(order, "Order", 3, 7, B_UNITS_FORMULA)
    _set_formula(order, "Order", 3, 8, B_COST_FORMULA)
    (root / spec.FIXTURE_NAMES["brief"]).write_text(
        "# SKU-LAMP replenishment\n\n"
        "A calculates two-month net need from visible monthly sales and stock in individual units. "
        "B reads A's saved Calc revision, enters that need in individual units, decides how many "
        "whole cartons to buy, and checks the derived individual-unit count, cost, and budget. "
        "The order sheet labels cartons and individual units in separate columns.\n",
        encoding="utf-8")
    files = {
        name: {"sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(),
               "bytes": (root / name).stat().st_size}
        for name in spec.FIXTURE_NAMES.values()
    }
    manifest = {
        "case_id": spec.CASE_ID,
        "case_version": spec.CASE_VERSION,
        "fixture_sha256": files,
        "conditions": list(spec.CONDITIONS),
        "outputs": spec.OUTPUTS,
        "role_budgets": spec.ROLE_BUDGET,
    }
    (root / "fixture_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
