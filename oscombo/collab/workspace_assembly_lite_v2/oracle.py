"""Scoring-side artifact checks; GUI handoff is assessed separately."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from oscombo.collab.workspace_assembly.fixtures import read_odt
from . import spec
from .fixtures import draft_text
from .private.gold import EXPECTED_NAME, TAG_PATTERN


def evaluate(source_asset, incoming_asset, delivered_asset, draft_report, final_report) -> dict:
    source_asset, incoming_asset, delivered_asset = map(Path, (source_asset, incoming_asset, delivered_asset))
    try:
        source, delivered = source_asset.read_bytes(), delivered_asset.read_bytes()
        draft, _ = read_odt(draft_report)
        final, _ = read_odt(final_report)
        match = re.search(TAG_PATTERN, source.decode("utf-8"))
        if match is None:
            raise ValueError("source inspection tag missing")
        audience = re.search(r"(?im)^Prepared for ([A-Za-z][A-Za-z -]+?) review\.$", draft)
        if audience is None:
            raise ValueError("draft review audience missing")
    except (OSError, ValueError, KeyError, UnicodeError) as exc:
        return {"case_id": spec.CASE_ID, "case_version": spec.CASE_VERSION,
                "actors": {"A": {"success": False}, "B": {"success": False}},
                "joint_success": False, "invalid_artifact": type(exc).__name__}
    original, lines = draft_text().splitlines(), final.splitlines()
    a = {"delivered_name": delivered_asset.name == EXPECTED_NAME,
         "source_bytes_preserved": hashlib.sha256(source).digest() == hashlib.sha256(delivered).digest(),
         "incoming_source_moved": not incoming_asset.exists()}
    review = lines[2].casefold().strip() if len(lines) == 4 else ""
    attachment = lines[3].casefold() if len(lines) == 4 else ""
    token = match.group(1).casefold()
    b = {"draft_fixture_intact": draft.splitlines() == original,
         "draft_text_preserved": len(lines) == 4 and lines[:2] == original,
         "audience_matches_draft": bool(re.fullmatch(
             r"(?:audience|for):\s*" + re.escape(audience.group(1).casefold()) + r"(?:\s+team)?[.!]?", review)),
         "attachment_named": EXPECTED_NAME.casefold() in attachment,
         "tag_matches_source": bool(re.search(r"(?<![\w-])" + re.escape(token) + r"(?![\w-])", attachment)),
         "attachment_not_empty": bool(attachment.strip()),
         "asset_delivered": all(a.values())}
    return {"case_id": spec.CASE_ID, "case_version": spec.CASE_VERSION,
            "actors": {"A": {"success": all(a.values()), "checks": a},
                       "B": {"success": all(b.values()), "checks": b}},
            "joint_success": all(a.values()) and all(b.values()),
            "behavioral_handoff": "Review GUI and message traces separately; artifact success is not proof of reading."}
