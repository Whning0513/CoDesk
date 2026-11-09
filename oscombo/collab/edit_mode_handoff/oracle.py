"""Exact semantic Oracle for saved EDIT-1 Writer artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree as ET

from . import CASE_ID, CASE_VERSION
from .fixtures import NS, TEXT
from .spec import ACTOR_OUTPUTS, EXPECTED_LINES, SHARED_OUTPUT


def read_fodt(path: str | Path) -> list[str]:
    root = ET.parse(path).getroot()
    body = root.find(f"{{{NS}}}body/{{{NS}}}text")
    if body is None:
        raise ValueError("FODT has no office:text body")
    lines = []
    for paragraph in body.findall(f"{{{TEXT}}}p"):
        lines.append("".join(paragraph.itertext()))
    return lines


def _exact(lines: list[str]) -> bool:
    return tuple(lines) == EXPECTED_LINES


def evaluate(workspace: str | Path, topology: str) -> dict[str, object]:
    root = Path(workspace)
    if topology == "isolated":
        paths = {actor: root / filename for actor, filename in ACTOR_OUTPUTS.items()}
        outputs: dict[str, list[str] | None] = {}
        errors: dict[str, str] = {}
        for actor, path in paths.items():
            try:
                outputs[actor] = read_fodt(path)
            except (OSError, ET.ParseError, ValueError) as exc:
                outputs[actor] = None
                errors[actor] = f"{type(exc).__name__}: {exc}"
        actor_success = {
            "A": outputs["A"] is not None and outputs["A"][0] == EXPECTED_LINES[0]
                 and outputs["A"][2] == EXPECTED_LINES[2],
            "B": outputs["B"] is not None and outputs["B"][1] == EXPECTED_LINES[1]
                 and outputs["B"][2] == EXPECTED_LINES[2],
        }
        joint = all(actor_success.values())
        return {"case_id": CASE_ID, "case_version": CASE_VERSION, "topology": topology,
                "actor_success": actor_success, "joint_success": joint,
                "outputs": outputs, "errors": errors,
                "interpretation": "Both isolated documents are scored for their assigned edit; the peer's independent edit need not appear in each copy."}
    if topology != "shared":
        raise ValueError("topology must be 'isolated' or 'shared'")
    try:
        lines = read_fodt(root / SHARED_OUTPUT)
        valid = len(lines) == len(EXPECTED_LINES)
    except (OSError, ET.ParseError, ValueError) as exc:
        lines, valid = [], False
        errors = [f"{type(exc).__name__}: {exc}"]
    else:
        errors = []
    checks = {f"line_{index + 1}_exact": valid and actual == expected
              for index, (actual, expected) in enumerate(zip(lines, EXPECTED_LINES))}
    checks["line_count"] = valid
    return {"case_id": CASE_ID, "case_version": CASE_VERSION, "topology": topology,
            "actor_success": {"A": checks.get("line_1_exact", False),
                              "B": checks.get("line_2_exact", False)},
            "joint_success": valid and all(checks.values()), "checks": checks,
            "observed_lines": lines, "errors": errors}


def evaluate_controls(root: str | Path) -> dict[str, object]:
    base = Path(root)
    public_lines = read_fodt(base / "public" / "release_notice.fodt")
    gold_lines = read_fodt(base / "private" / "gold.fodt")
    negative_lines = read_fodt(
        base / "private" / "negative_overwrite_signature" / "release_notice.fodt")
    return {"public_is_initial": public_lines != EXPECTED_LINES,
            "gold_joint_pass": _exact(gold_lines),
            "overwrite_negative_fail": not _exact(negative_lines),
            "overwrite_signature": negative_lines[0],
            "controls_pass": public_lines != EXPECTED_LINES and _exact(gold_lines)
                             and not _exact(negative_lines)}
