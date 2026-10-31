"""Scoring-side local role checks; GUI handoff is assessed separately."""
from __future__ import annotations

import hashlib
import io
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from . import spec
from .fixtures import draft_text
from .private.gold import EXPECTED_NAME, TAG_PATTERN

TEXT_NS = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"


def _odt_text(data: bytes) -> str:
    """Parse immutable bytes so host I/O errors are not hidden by format checks."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if archive.read("mimetype").decode("utf-8") != "application/vnd.oasis.opendocument.text":
            raise ValueError("not a real OpenDocument Text file")
        root = ET.fromstring(archive.read("content.xml"))
    paragraphs = ["".join(node.itertext()) for node in root.iter()
                  if node.tag in {f"{{{TEXT_NS}}}p", f"{{{TEXT_NS}}}h"}]
    return "\n".join(paragraphs)


def _canonical(text: str) -> str:
    return " ".join("".join(" " if unicodedata.category(c).startswith("P") else c
                            for c in text.casefold()).split())


def _unknown(kind: str, exc: Exception, actors: dict | None = None) -> dict:
    return {"case_id": spec.CASE_ID, "case_version": spec.CASE_VERSION,
            "actors": actors or {"A": {"success": None}, "B": {"success": None}},
            "joint_success": None, kind: type(exc).__name__}


def evaluate(source_asset, incoming_asset, delivered_asset, draft_report, final_report) -> dict:
    source_asset, incoming_asset, delivered_asset = map(Path, (source_asset, incoming_asset, delivered_asset))
    try:
        source = source_asset.read_bytes()
        draft = _odt_text(Path(draft_report).read_bytes())
        match = re.search(TAG_PATTERN, source.decode("utf-8"))
        audience = re.search(r"(?im)^Prepared for ([A-Za-z][A-Za-z -]+?) review\.$", draft)
        if match is None or audience is None or draft.splitlines() != draft_text().splitlines():
            raise ValueError("invalid public source or draft fixture")
    except FileNotFoundError as exc:
        return _unknown("invalid_fixture", exc)
    except OSError as exc:
        return _unknown("invalid_scorer", exc)
    except (ValueError, KeyError, UnicodeError, ET.ParseError, zipfile.BadZipFile) as exc:
        return _unknown("invalid_fixture", exc)

    original = draft.splitlines()
    a_error = None
    try:
        delivered = delivered_asset.read_bytes()
    except (FileNotFoundError, IsADirectoryError) as exc:
        delivered = None
        a_error = type(exc).__name__
    except OSError as exc:
        return _unknown("invalid_scorer", exc)
    try:
        incoming_asset.stat()
        incoming_present = True
    except FileNotFoundError:
        incoming_present = False
    except OSError as exc:
        return _unknown("invalid_scorer", exc)
    a = {"delivered_present": delivered is not None,
         "delivered_name": delivered_asset.name == EXPECTED_NAME,
         "source_bytes_preserved": delivered is not None and hashlib.sha256(source).digest() == hashlib.sha256(delivered).digest(),
         "incoming_source_moved": not incoming_present}
    actor_a = {"success": all(a.values()), "checks": a}
    if a_error:
        actor_a["artifact_error"] = a_error

    try:
        final_bytes = Path(final_report).read_bytes()
    except (FileNotFoundError, IsADirectoryError) as exc:
        actor_b = {"success": False, "checks": {"artifact_readable": False}, "artifact_error": type(exc).__name__}
    except OSError as exc:
        return _unknown("invalid_scorer", exc, {"A": actor_a, "B": {"success": None}})
    else:
        try:
            lines = [line.strip() for line in _odt_text(final_bytes).splitlines() if line.strip()]
        except (ValueError, KeyError, UnicodeError, ET.ParseError, zipfile.BadZipFile) as exc:
            actor_b = {"success": False, "checks": {"artifact_readable": False}, "artifact_error": type(exc).__name__}
        else:
            review = lines[2].casefold().strip() if len(lines) == 4 else ""
            attachment = lines[3].casefold() if len(lines) == 4 else ""
            token = match.group(1).casefold()
            b = {"artifact_readable": True,
                 "draft_text_preserved": len(lines) == 4 and [_canonical(x) for x in lines[:2]] == [_canonical(x) for x in original],
                 "audience_matches_draft": bool(re.fullmatch(
                     r"(?:audience|for)\s*[:：—-]\s*" + re.escape(audience.group(1).casefold()) + r"(?:\s+team)?[.!。]?", review)),
                 "attachment_named": bool(re.search(r"(?<![\w.-])" + re.escape(EXPECTED_NAME.casefold()) + r"(?![\w-]|\.[\w-])", attachment)),
                 "tag_matches_source": bool(re.search(r"(?<![\w-])" + re.escape(token) + r"(?![\w-])", attachment)),
                 "attachment_not_empty": bool(attachment.strip())}
            actor_b = {"success": all(b.values()), "checks": b}
    return {"case_id": spec.CASE_ID, "case_version": spec.CASE_VERSION,
            "actors": {"A": actor_a, "B": actor_b},
            "joint_success": actor_a["success"] and actor_b["success"],
            "behavioral_handoff": "Review GUI and message traces separately; artifact success is not proof of reading."}
