"""Private positive control for Case 6 v1.3; never place in Actor inputs."""
from __future__ import annotations

import math
from pathlib import Path

from oscombo.collab.data_to_deck.fixtures import _ods
from .. import fixtures, spec


A_NEED_FORMULA = "of:=MAX(0;([.B3]+[.C3]+[.D3])/3*2+[.G3]-[.E3]-[.F3])"
B_UNITS_FORMULA = fixtures.B_UNITS_FORMULA
B_COST_FORMULA = fixtures.B_COST_FORMULA


def expected_plan() -> tuple[int, int, int, int]:
    forecast = fixtures.forecast_rows()[2]
    order = fixtures.order_rows()[2]
    need = max(0, sum(forecast[1:4]) / 3 * 2 + forecast[6] - forecast[4] - forecast[5])
    cartons = math.ceil(need / order[1])
    units = cartons * order[1]
    cost = units * order[2]
    return int(need), int(cartons), int(units), int(cost)


def write_gold(forecast_path: str | Path, order_path: str | Path) -> None:
    """Write evaluator-only correct outputs, preserving the public formulas."""
    need, cartons, units, cost = expected_plan()
    forecast_rows = fixtures.forecast_rows()
    forecast_rows[2].append(need)
    _ods(Path(forecast_path), {"Forecast": forecast_rows})
    fixtures._set_formula(Path(forecast_path), "Forecast", 3, 8, A_NEED_FORMULA)

    order_rows = fixtures.order_rows()
    order_rows[2][4:8] = [need, cartons, units, cost]
    _ods(Path(order_path), {"Order": order_rows})
    fixtures._set_formula(Path(order_path), "Order", 3, 7, B_UNITS_FORMULA)
    fixtures._set_formula(Path(order_path), "Order", 3, 8, B_COST_FORMULA)


if __name__ == "__main__":
    print({"private_expected_plan": expected_plan(), "case_id": spec.CASE_ID})
