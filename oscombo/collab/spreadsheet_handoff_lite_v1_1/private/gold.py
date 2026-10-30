"""Evaluator-side expected values derived from the public source cells."""
from __future__ import annotations

import math
from pathlib import Path

from oscombo.collab.data_to_deck.fixtures import _ods
from ..fixtures import forecast_rows, order_rows


def expected_plan() -> tuple[int, int, int]:
    forecast = forecast_rows()[2]
    order = order_rows()[2]
    need = max(0, sum(forecast[1:4]) / 3 * 2 + forecast[6] - forecast[4] - forecast[5])
    units = math.ceil(need / order[1]) * order[1]
    return int(need), int(units), int(units * order[2])


def write_gold(forecast_path: str | Path, order_path: str | Path) -> None:
    need, units, cost = expected_plan()
    forecast = forecast_rows()
    forecast[2][7:9] = [need, "B3:G3"]
    order = order_rows()
    order[2][4:6] = [units, cost]
    _ods(Path(forecast_path), {"Forecast": forecast})
    _ods(Path(order_path), {"Order": order})
