"""Versioned public workbooks for the Calc revision handoff."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from oscombo.collab.data_to_deck.fixtures import NS, _ods
from . import spec


def forecast_rows() -> list[list[object]]:
    return [["SKU-LAMP | two-month need | units"],
            ["SKU", "Jun sales", "Jul sales", "Aug sales", "On hand", "Inbound", "Safety", "NET NEED", "Source reference"],
            ["SKU-LAMP", 40, 50, 60, 39, 18, 30, "", "Sales B3:D3; stock E3:F3; safety G3"]]


def order_rows() -> list[list[object]]:
    return [["SKU-LAMP | purchase plan | units and USD"],
            ["SKU", "Units / case", "USD / unit", "Budget USD", "ORDER UNITS", "Cost USD", "Source"],
            ["SKU-LAMP", 10, 28, 2300, "", "", "forecast.ods"]]


def _set_public_layout(path: Path, sheet: str, cursor_column: int) -> None:
    """Increase default grid font and cell dimensions without changing data."""
    for prefix in ("office", "table", "text", "style", "fo"):
        ET.register_namespace(prefix, NS[prefix])
    with zipfile.ZipFile(path) as z:
        members = [(i, z.read(i.filename)) for i in z.infolist()]
    root = ET.fromstring(dict((i.filename, data) for i, data in members)["content.xml"])
    q = lambda ns, local: f"{{{NS[ns]}}}{local}"
    styles = ET.Element(q("office", "automatic-styles"))
    col = ET.SubElement(styles, q("style", "style"), {q("style", "name"): "wide", q("style", "family"): "table-column"})
    ET.SubElement(col, q("style", "table-column-properties"), {q("style", "column-width"): "3.8cm"})
    row = ET.SubElement(styles, q("style", "style"), {q("style", "name"): "tall", q("style", "family"): "table-row"})
    ET.SubElement(row, q("style", "table-row-properties"), {q("style", "row-height"): "0.85cm"})
    cell = ET.SubElement(styles, q("style", "style"), {q("style", "name"): "legible", q("style", "family"): "table-cell"})
    ET.SubElement(cell, q("style", "text-properties"), {q("fo", "font-size"): "14pt"})
    root.insert(0, styles)
    for table in root.findall(f".//{q('table','table')}"):
        table.insert(0, ET.Element(q("table", "table-column"), {q("table", "style-name"): "wide", q("table", "number-columns-repeated"): "9", q("table", "default-cell-style-name"): "legible"}))
        for table_row in table.findall(q("table", "table-row")):
            table_row.set(q("table", "style-name"), "tall")
            for cell_node in table_row.findall(q("table", "table-cell")):
                paragraphs = cell_node.findall(q("text", "p"))
                if cell_node.get(q("office", "value-type")) == "string" and len(paragraphs) == 1 and not (paragraphs[0].text or ""):
                    cell_node.attrib.pop(q("office", "value-type"))
                    cell_node.remove(paragraphs[0])
    updated = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    settings = f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-settings xmlns:office="{NS['office']}" xmlns:config="urn:oasis:names:tc:opendocument:xmlns:config:1.0" xmlns:ooo="http://openoffice.org/2004/office" office:version="1.2">
 <office:settings><config:config-item-set config:name="ooo:view-settings">
  <config:config-item-map-indexed config:name="Views"><config:config-item-map-entry>
   <config:config-item config:name="ViewId" config:type="string">view1</config:config-item>
   <config:config-item-map-named config:name="Tables"><config:config-item-map-entry config:name="{sheet}">
    <config:config-item config:name="CursorPositionX" config:type="int">{cursor_column}</config:config-item>
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
   <config:config-item config:name="ActiveTable" config:type="string">{sheet}</config:config-item>
   <config:config-item config:name="ZoomType" config:type="short">0</config:config-item>
   <config:config-item config:name="ZoomValue" config:type="int">100</config:config-item>
  </config:config-item-map-entry></config:config-item-map-indexed>
 </config:config-item-set></office:settings></office:document-settings>'''.encode()
    with zipfile.ZipFile(path, "w") as z:
        for info, data in members:
            payload = updated if info.filename == "content.xml" else settings if info.filename == "settings.xml" else data
            z.writestr(info, payload)


def build_fixture(root: str | Path) -> dict:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise FileExistsError(f"Lite fixture destination is not empty: {root}")
    _ods(root / spec.FIXTURE_NAMES["forecast"], {"Forecast": forecast_rows()})
    _ods(root / spec.FIXTURE_NAMES["order"], {"Order": order_rows()})
    for key, sheet, cursor in (("forecast", "Forecast", 7), ("order", "Order", 5)):
        _set_public_layout(root / spec.FIXTURE_NAMES[key], sheet, cursor)
    (root / spec.FIXTURE_NAMES["brief"]).write_text(
        "# SKU-LAMP replenishment\n\n"
        "A calculates two-month non-negative need from the visible three monthly sales and stock data. "
        "B prepares a general cost formula before handoff, then reads A's saved revision in Calc and "
        "orders the smallest whole-case multiple within the budget. A's ready message must not disclose the number. "
        "The saved revision, not a message, is B's evidence.\n", encoding="utf-8")
    files = {name: {"sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(),
                    "bytes": (root / name).stat().st_size}
             for name in spec.FIXTURE_NAMES.values()}
    manifest = {"case_id": spec.CASE_ID, "case_version": spec.CASE_VERSION,
                "fixture_sha256": files, "conditions": spec.CONDITIONS,
                "outputs": spec.OUTPUTS, "role_budgets": spec.ROLE_BUDGET}
    (root / "fixture_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
