"""Independent Blender re-open and report-consistency Oracle for MAR Lite v1."""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import tempfile
from pathlib import Path

from . import gold, spec
from oscombo.collab.model_and_review.blend_format import has_blend_container_header_at


def snapshot_blend(path: Path, blender_bin: str) -> dict:
    if not path.is_file() or not has_blend_container_header_at(path):
        raise ValueError(f"missing or invalid Blender container: {path}")
    script = Path(__file__).with_name("blender_snapshot.py")
    with tempfile.TemporaryDirectory(prefix="codesk-mar-lite-score-") as temp:
        output = Path(temp) / "snapshot.json"
        scorer_env = {key: os.environ[key] for key in ("PATH", "HOME", "TMPDIR") if key in os.environ}
        scorer_env["OMP_NUM_THREADS"] = "2"
        completed = subprocess.run([blender_bin, "--background", "--factory-startup",
                                    "--disable-autoexec",
                                    str(path.resolve()),
                                    "--python", str(script), "--", "--output", str(output)],
                                   capture_output=True, text=True, timeout=120, env=scorer_env)
        if completed.returncode or not output.exists():
            raise RuntimeError("Blender could not reopen scored project: " +
                               (completed.stderr[-1200:] or completed.stdout[-1200:]))
        return json.loads(output.read_text())


def _close(actual, expected, tolerance=0.01) -> bool:
    try:
        return math.isfinite(float(actual)) and abs(float(actual) - expected) <= tolerance
    except (TypeError, ValueError):
        return False


def _field(text: str, english: str, chinese: str) -> float | None:
    match = re.search(rf"(?:{english}|{chinese})\s*[:：=]\s*([0-9]+(?:\.[0-9]+)?)",
                      text, re.IGNORECASE)
    return float(match.group(1)) if match else None


def evaluate_snapshots(initial: dict, final: dict, report: str) -> dict:
    first = initial.get("objects", {})
    last = final.get("objects", {})
    names_ok = (initial.get("scene_name") == final.get("scene_name") == gold.SCENE_NAME
                and set(first) == set(last) == gold.OBJECT_NAMES)
    shade_initial = first.get("Lamp_Shade", {})
    shade_final = last.get("Lamp_Shade", {})
    bulb = last.get("Lamp_Bulb", {})
    initial_width_ok = _close((shade_initial.get("dimensions") or [None])[0],
                              gold.INITIAL_SHADE_WIDTH_M)
    final_dims = shade_final.get("dimensions") or []
    width = float(final_dims[0]) if len(final_dims) == 3 else math.nan
    height = float(final_dims[2]) if len(final_dims) == 3 else math.nan
    bulb_dims = bulb.get("dimensions") or []
    bulb_width = float(bulb_dims[0]) if len(bulb_dims) == 3 else math.nan
    clearance = (width - bulb_width) / 2
    shade_ok = (initial_width_ok and len(final_dims) == 3
                and _close(width, gold.TARGET_SHADE_WIDTH_M)
                and _close(final_dims[1], gold.TARGET_SHADE_WIDTH_M)
                and _close(height, gold.SHADE_HEIGHT_M)
                and shade_final.get("mesh_sha256") == shade_initial.get("mesh_sha256")
                and shade_final.get("materials") == shade_initial.get("materials")
                and shade_final.get("location") == shade_initial.get("location")
                and shade_final.get("rotation") == shade_initial.get("rotation"))
    protected_ok = all(last.get(name) == first.get(name) for name in gold.PROTECTED_OBJECTS)
    reported_width = _field(report, r"(?:shade\s*(?:outer\s*)?width|outer\s*width)",
                            r"灯罩(?:宽度|外宽|外径)")
    reported_clearance = _field(report, r"(?:radial\s*clearance|bulb\s*clearance|clearance)",
                                r"(?:径向净空|灯泡净空)")
    verdict_match = re.search(r"(?:verdict|result|judgment|结论|判定)\s*[:：=]\s*(pass|fail|adequate|inadequate|达标|不达标|通过|未通过)",
                              report, re.IGNORECASE)
    verdict = verdict_match.group(1).casefold() if verdict_match else None
    should_pass = clearance + 1e-6 >= gold.MIN_RADIAL_CLEARANCE_M
    verdict_ok = verdict in ({"pass", "adequate", "达标", "通过"} if should_pass
                              else {"fail", "inadequate", "不达标", "未通过"})
    review_ok = (reported_width is not None and reported_clearance is not None
                 and _close(reported_width, width, 0.02)
                 and _close(reported_clearance, clearance, 0.02)
                 and verdict_ok)
    checks = {"scene_inventory": names_ok, "A_shade_geometry": shade_ok,
              "protected_objects": protected_ok, "B_report_matches_saved_scene": review_ok}
    a_ok = names_ok and shade_ok and protected_ok
    joint = a_ok and review_ok
    return {"case_id": spec.CASE_ID, "oracle_version": "1.0.0",
            "status": "PASS" if joint else "FAIL", "joint_success": joint,
            "actor_subscores": {"A": a_ok, "B": review_ok}, "checks": checks,
            "measured": {"shade_width_m": width if math.isfinite(width) else None,
                         "bulb_width_m": bulb_width if math.isfinite(bulb_width) else None,
                         "radial_clearance_m": clearance if math.isfinite(clearance) else None,
                         "reported_width_m": reported_width,
                         "reported_clearance_m": reported_clearance,
                         "reported_verdict": verdict}}


def evaluate(initial_blend: Path, final_blend: Path, initial_report: Path,
             final_report: Path, blender_bin: str) -> dict:
    # The initial report is part of the public fixture contract, but only the
    # final saved text is scored. Keep both paths explicit for adapter parity.
    if not initial_report.is_file():
        raise FileNotFoundError(initial_report)
    initial = snapshot_blend(initial_blend, blender_bin)
    try:
        final = snapshot_blend(final_blend, blender_bin)
    except (ValueError, RuntimeError) as exc:
        # A malformed/missing Actor save is a task failure. The public initial
        # fixture was successfully reopened above, so the scorer is available.
        return {"case_id": spec.CASE_ID, "oracle_version": "1.0.0", "status": "FAIL",
                "joint_success": False, "actor_subscores": {"A": False, "B": False},
                "checks": {"A_blender_artifact_reopens": False},
                "artifact_error": f"{type(exc).__name__}: {exc}"}
    report = final_report.read_text(encoding="utf-8") if final_report.exists() else ""
    return evaluate_snapshots(initial, final, report)
