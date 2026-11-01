"""Scoring patterns; the code is derived from the host-held public source."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

EXPECTED_NAME = "inspection_note.txt"
TAG_PATTERN = r"(?m)^Inspection code: ([2-9]{3})\.$"


def build_gold(root: str | Path, fixture_root: str | Path) -> dict:
    """Create scoring-side positive outputs; never install them in an Actor Guest."""
    from .. import fixtures

    root, fixture_root = Path(root), Path(fixture_root)
    source = (fixture_root / EXPECTED_NAME).read_bytes()
    match = re.search(TAG_PATTERN, source.decode("utf-8"))
    if match is None:
        raise ValueError("fixture inspection code is missing")
    root.mkdir(parents=True, exist_ok=False)
    delivered = root / EXPECTED_NAME
    delivered.write_bytes(source)
    report = root / "handoff_report.odt"
    fixtures.report_odt(report, "Audience: Operations", f"Inspection code: {match.group(1)}")
    result = {name: {"sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(),
                     "bytes": (root / name).stat().st_size}
              for name in (EXPECTED_NAME, report.name)}
    (root / "gold_manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
