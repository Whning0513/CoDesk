"""Read-only artifact Oracle; browser behavior is separately checked in GUI traces."""
from __future__ import annotations

import re
from pathlib import Path

from . import spec
from .fixtures import qa_template, source_html
from .private.gold import EXPECTED_FILTER


def evaluate(source_path: str | Path, saved_source_path: str | Path,
             qa_template_path: str | Path, qa_note_path: str | Path) -> dict:
    try:
        source = Path(source_path).read_text(encoding="utf-8")
        saved = Path(saved_source_path).read_text(encoding="utf-8")
        template = Path(qa_template_path).read_text(encoding="utf-8")
        note = Path(qa_note_path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return {"case_id": spec.CASE_ID, "case_version": spec.CASE_VERSION,
                "actors": {"A": {"success": False}, "B": {"success": False}},
                "joint_success": False, "invalid_artifact": type(exc).__name__}
    corrected = source.replace('value="delievered"', 'value="delivered"', 1)
    # GNOME Text Editor may auto-indent pasted/typewritten lines. That does
    # not change this static page's behavior, so compare line content while
    # preserving all non-leading characters and their order.
    significant_lines = lambda text: [line.strip() for line in text.splitlines() if line.strip()]
    a_checks = {
        "public_source_intact": source == source_html(),
        "delivered_option_repaired": corrected != source and
                                     significant_lines(saved) == significant_lines(corrected),
    }
    values = {}
    for field in ("Query", "Status", "Visible order IDs", "Saved source"):
        match = re.search(rf"(?im)^\s*{re.escape(field)}\s*:\s*(.*?)\s*$", note)
        values[field] = match.group(1).strip() if match else ""
    expected = EXPECTED_FILTER
    observed_ids = tuple(re.findall(r"\bOD-\d+\b", values["Visible order IDs"], re.I))
    b_checks = {
        "public_template_intact": template == qa_template(),
        "query_recorded": values["Query"].casefold() == expected["query"],
        "status_recorded": values["Status"].casefold() == expected["status"],
        "visible_ids_correct": observed_ids == expected["visible_ids"],
        "names_saved_source": values["Saved source"].casefold() == "orderdesk.html",
        "source_repaired_for_test": all(a_checks.values()),
    }
    a_success, b_success = all(a_checks.values()), all(b_checks.values())
    return {"case_id": spec.CASE_ID, "case_version": spec.CASE_VERSION,
            "actors": {"A": {"success": a_success, "checks": a_checks},
                       "B": {"success": b_success, "checks": b_checks}},
            "joint_success": a_success and b_success,
            "behavioral_handoff": "Requires browser screenshots after A's saved revision and message; artifact text alone is insufficient"}
