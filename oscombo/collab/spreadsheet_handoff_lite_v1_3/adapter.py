"""Version-pinned scripted controls and evidence gates for Case 6 Lite v1.3.1.

This module is host-side orchestration only. It does not expose Gold or Oracle
data to either actor. Importing it never starts a Guest or contacts a model API.
"""
from __future__ import annotations

import hashlib
import re
import struct
from pathlib import Path

from . import fixtures, oracle, spec


def select_case(case_version: str):
    """Return the exact v1.3.1 package; reject implicit fallback to old versions."""
    if case_version != spec.CASE_VERSION:
        raise ValueError(f"unsupported Spreadsheet Handoff version: {case_version!r}")
    return spec, fixtures, oracle


def scripted_actions(negative: bool = False) -> dict[str, list[str]]:
    """GUI actions for the deterministic controls, not for model episodes."""
    forecast_formula = (
        "=MAX(0;((B3+C3+D3)/3)*2+G3-E3-F3)" if not negative else
        "=MAX(0;((B3+C3+D3)/3)*2+G3-E3-F3-8)"
    )
    # In the negative control A's saved formula yields 65; B follows that
    # delivered value coherently, so the Oracle detects the bad forecast.
    need, cartons = (65, 7) if negative else (73, 8)
    return {
        "A": [
            f"import pyautogui, time; pyautogui.write({forecast_formula!r}, interval=0.02)",
            "import pyautogui, time; pyautogui.press('enter'); time.sleep(1)",
            "import pyautogui, time; pyautogui.hotkey('ctrl','s'); time.sleep(2)",
            "DONE",
        ],
        "B_read": [
            # `peer_path` is inserted by peer_read_actions after A publishes.
        ],
        "B_order": [
            "import pyautogui, time; pyautogui.hotkey('alt','tab'); time.sleep(1)",
            f"import pyautogui, time; pyautogui.write({str(need)!r}, interval=0.05); pyautogui.press('tab'); time.sleep(0.5)",
            f"import pyautogui, time; pyautogui.write({str(cartons)!r}, interval=0.05); pyautogui.press('enter'); time.sleep(1)",
            "import pyautogui, time; pyautogui.hotkey('ctrl','s'); time.sleep(2)",
            "DONE",
        ],
    }


def peer_read_actions(peer_guest_path: str) -> list[str]:
    """Open a published revision with Calc, using the complete peer-view path."""
    if not peer_guest_path.startswith(spec.TASK_ROOT + "/incoming/A/"):
        raise ValueError("peer revision must be inside the v1.3.1 incoming/A view")
    return [
        "import pyautogui, time; pyautogui.hotkey('ctrl','o'); time.sleep(1)",
        # GTK's Open dialog does not focus its location field by default. The
        # old action typed the path without focusing it, leaving the dialog
        # open while the title probe could still see the workbook behind it.
        f"import pyautogui, time; pyautogui.hotkey('ctrl','l'); time.sleep(0.5); pyautogui.write({peer_guest_path!r}, interval=0.02); pyautogui.press('enter'); time.sleep(5)",
        "DONE",
    ]


def verify_handoff(*, revision: dict, peer_sha256: str | None,
                   received_message_ids: set[str], message_id: str,
                   peer_guest_path: str, gui_action_trace: list[dict],
                   active_window: str, screenshot_path: str | Path,
                   published_at: float, message_received_at: float,
                   gui_read_at: float, order_edit_at: float,
                   order_saved_at: float) -> dict:
    """Require delivered bytes, delivered message, exact GUI-opened revision,
    and chronology. A revision/hash string alone cannot pass this gate.
    """
    reasons: list[str] = []
    revision_no = revision.get("revision") if isinstance(revision, dict) else None
    expected_sha = revision.get("sha256") if isinstance(revision, dict) else None
    rel_path = revision.get("peer_view_path") if isinstance(revision, dict) else None
    if (not isinstance(revision, dict) or revision.get("actor") != "A"
            or not revision.get("delivered")
            or not isinstance(revision_no, int) or revision_no < 0):
        reasons.append("A_revision_not_committed_and_delivered")
    if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        reasons.append("invalid_revision_sha256")
    if peer_sha256 != expected_sha:
        reasons.append("peer_revision_bytes_do_not_match")
    if not isinstance(rel_path, str) or peer_guest_path != f"{spec.TASK_ROOT}/{rel_path}":
        reasons.append("peer_path_is_not_the_published_revision")
    elif (not isinstance(revision_no, int)
          or not Path(rel_path).stem.endswith(f"-r{revision_no:06d}")):
        reasons.append("peer_view_filename_revision_mismatch")
    if message_id not in received_message_ids:
        reasons.append("A_ready_message_not_received_by_B")

    actions = [str(row.get("code", "")) for row in gui_action_trace if isinstance(row, dict)]
    open_action_seen = any(re.search(
        r"hotkey\(\s*['\"]ctrl['\"]\s*,\s*['\"]o['\"]", code, re.I)
        for code in actions)
    exact_path_entered = any(peer_guest_path in code for code in actions)
    if not open_action_seen or not exact_path_entered:
        reasons.append("GUI_trace_does_not_open_exact_peer_revision")
    if Path(peer_guest_path).name.casefold() not in (active_window or "").casefold():
        reasons.append("peer_revision_not_visible_in_active_GUI_window")
    if "read-only" not in (active_window or "").casefold():
        reasons.append("peer_revision_not_open_read_only")
    shot = Path(screenshot_path)
    png = shot.read_bytes() if shot.is_file() else b""
    if (len(png) < 24 or not png.startswith(b"\x89PNG\r\n\x1a\n")
            or struct.unpack(">II", png[16:24]) != (1920, 1080)):
        reasons.append("missing_post_open_GUI_screenshot")
    if not (published_at <= message_received_at <= gui_read_at <= order_edit_at <= order_saved_at):
        reasons.append("handoff_and_order_edit_chronology_invalid")
    return {"valid": not reasons, "reasons": reasons,
            "revision": revision_no, "sha256": expected_sha,
            "peer_guest_path": peer_guest_path,
            "active_window": active_window,
            "screenshot": str(screenshot_path)}


def map_scripted_result(*, oracle_result: dict, actor_results: dict,
                        handoff: dict, postscore_lifecycle_ok: bool,
                        reset_ok: bool, bridge_ok: bool = True) -> str:
    """Separate scored task failures from unusable scripted/infra runs."""
    if (not reset_ok or not bridge_ok or not postscore_lifecycle_ok
            or not handoff.get("valid")):
        return "INVALID_INFRA_OR_RUNNER_ERROR"
    if any(actor_results.get(role, {}).get("status") != "done" for role in "AB"):
        return "INVALID_INFRA_OR_RUNNER_ERROR"
    return "PASS" if bool(oracle_result.get("joint_success")) else "FAIL"


def sha256_bytes(payload: bytes) -> str:
    """Small public helper used by the Guest adapter and offline tests."""
    return hashlib.sha256(payload).hexdigest()
