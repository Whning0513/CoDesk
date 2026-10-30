"""Read-only one-asset and Writer artifact Oracle."""
from __future__ import annotations

import hashlib
from pathlib import Path

from oscombo.collab.workspace_assembly.fixtures import read_odt
from . import spec
from .fixtures import asset_text, draft_text
from .private.gold import EXPECTED_NAME, EXPECTED_TAG


def evaluate(source_asset: str | Path, incoming_asset: str | Path,
             delivered_asset: str | Path, draft_report: str | Path,
             final_report: str | Path) -> dict:
    source_asset, incoming_asset, delivered_asset = map(Path, (source_asset, incoming_asset, delivered_asset))
    try:
        source = source_asset.read_bytes()
        delivered = delivered_asset.read_bytes()
        draft, _ = read_odt(draft_report)
        final, _ = read_odt(final_report)
    except (OSError, ValueError, KeyError) as exc:
        return {"case_id": spec.CASE_ID, "case_version": spec.CASE_VERSION,
                "actors": {"A": {"success": False}, "B": {"success": False}},
                "joint_success": False, "invalid_artifact": type(exc).__name__}
    a_checks = {
        "source_fixture_intact": source.decode("utf-8", errors="replace") == asset_text(),
        "delivered_name": delivered_asset.name == EXPECTED_NAME,
        "attachment_bytes_preserved": hashlib.sha256(source).digest() == hashlib.sha256(delivered).digest(),
        "incoming_source_moved": not incoming_asset.exists(),
    }
    initial_lines = draft_text().splitlines()
    lines = final.splitlines()
    middle = lines[1].casefold() if len(lines) == 3 else ""
    b_checks = {
        "real_writer_report": bool(lines),
        "draft_intact": draft.splitlines() == initial_lines,
        "title_and_closing_preserved": len(lines) == 3 and lines[0] == initial_lines[0] and lines[2] == initial_lines[2],
        "attachment_named": EXPECTED_NAME.casefold() in middle,
        "correct_delivered_tag": EXPECTED_TAG.casefold() in middle,
        "placeholder_resolved": "[await" not in middle,
        "asset_verified_for_handoff": all(a_checks.values()),
    }
    a_success, b_success = all(a_checks.values()), all(b_checks.values())
    return {"case_id": spec.CASE_ID, "case_version": spec.CASE_VERSION,
            "actors": {"A": {"success": a_success, "checks": a_checks},
                       "B": {"success": b_success, "checks": b_checks}},
            "joint_success": a_success and b_success,
            "behavioral_handoff": "Audit A's file-manager move, revision transfer, B's GUI read and message chronology separately"}
