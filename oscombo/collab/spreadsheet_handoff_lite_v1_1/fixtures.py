"""Deterministic public Calc files for the short replenishment handoff."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from oscombo.collab.data_to_deck.fixtures import _ods
from . import spec


def forecast_rows() -> list[list[object]]:
    return [
        ["SKU-LAMP | two-month replenishment | all quantities in units"],
        ["SKU", "Jun units", "Jul units", "Aug units", "On hand units", "Inbound units", "Safety units", "Net need units", "Source cells"],
        ["SKU-LAMP", 40, 50, 60, 39, 18, 30, "", ""],
    ]


def order_rows() -> list[list[object]]:
    return [
        ["SKU-LAMP | purchase plan | enter order UNITS, not case count"],
        ["SKU", "Units per case", "USD per unit", "Budget USD", "ORDER UNITS", "Total cost USD", "Source"],
        ["SKU-LAMP", 10, 28, 2300, "", "", "forecast.ods"],
    ]


def build_fixture(root: str | Path) -> dict:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise FileExistsError(f"Lite fixture destination is not empty: {root}")
    _ods(root / spec.FIXTURE_NAMES["forecast"], {"Forecast": forecast_rows()})
    _ods(root / spec.FIXTURE_NAMES["order"], {"Order": order_rows()})
    (root / spec.FIXTURE_NAMES["brief"]).write_text(
        "# SKU-LAMP replenishment\n\n"
        "A checks the two-month net need from visible June–August sales and inventory. "
        "Use average monthly sales times two plus safety stock minus on-hand and inbound stock; "
        "do not order a negative quantity. B uses A's saved result to buy the smallest whole "
        "number of cases that covers the need, enters the resulting number of UNITS in E3, "
        "multiplies those units by the USD-per-unit price in C3 for F3, and checks the visible cap. "
        "Both output workbooks are already open. Save, publish and communicate through the "
        "same tools in Shared and Isolated. Each role edits only its own output.\n",
        encoding="utf-8")
    files = {name: {"sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(),
                    "bytes": (root / name).stat().st_size}
             for name in spec.FIXTURE_NAMES.values()}
    manifest = {"case_id": spec.CASE_ID, "case_version": spec.CASE_VERSION,
                "fixture_sha256": files, "conditions": spec.CONDITIONS,
                "outputs": spec.OUTPUTS, "role_budgets": spec.ROLE_BUDGET}
    (root / "fixture_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
