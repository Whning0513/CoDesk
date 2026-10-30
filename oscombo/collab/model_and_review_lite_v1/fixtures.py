"""Copy immutable public Lite fixtures into each run; never stage Gold."""
from __future__ import annotations

import shutil
from pathlib import Path

from . import spec


ROOT = Path(__file__).with_name("fixtures")


def build_fixture(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=False)
    for name in spec.FIXTURE_NAMES.values():
        shutil.copy2(ROOT / name, target / name)
