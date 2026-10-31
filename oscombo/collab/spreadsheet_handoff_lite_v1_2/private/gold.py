"""Scoring-side positive control; never stage in Actor Guests."""
from __future__ import annotations

import math
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from oscombo.collab.data_to_deck.fixtures import NS, _ods
from ..fixtures import forecast_rows, order_rows


def expected_plan() -> tuple[int, int, int]:
    forecast, order = forecast_rows()[2], order_rows()[2]
    need = max(0, sum(forecast[1:4]) / 3 * 2 + forecast[6] - forecast[4] - forecast[5])
    units = math.ceil(need / order[1]) * order[1]
    return int(need), int(units), int(units * order[2])


def write_gold(forecast_path: str | Path, order_path: str | Path) -> None:
    need, units, cost = expected_plan()
    forecast, order = forecast_rows(), order_rows()
    forecast[2][7] = need
    order[2][4:6] = [units, cost]
    _ods(Path(forecast_path), {"Forecast": forecast})
    path = Path(order_path)
    _ods(path, {"Order": order})
    with zipfile.ZipFile(path) as z:
        members = [(info, z.read(info.filename)) for info in z.infolist()]
    content = next(data for info, data in members if info.filename == "content.xml")
    root = ET.fromstring(content)
    # Formula values use the ODF OpenFormula prefix as lexical text; ElementTree
    # otherwise omits its declaration because no element uses that namespace.
    root.set("xmlns:of", "urn:oasis:names:tc:opendocument:xmlns:of:1.2")
    q = lambda ns, name: f"{{{NS[ns]}}}{name}"
    table = root.find(f".//{q('table','table')}")
    assert table is not None
    rows = table.findall(q("table", "table-row"))
    cells = rows[2].findall(q("table", "table-cell"))
    cells[5].set(q("table", "formula"), "of:=[.E3]*[.C3]")
    updated = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(path, "w") as z:
        for info, data in members:
            z.writestr(info, updated if info.filename == "content.xml" else data)
