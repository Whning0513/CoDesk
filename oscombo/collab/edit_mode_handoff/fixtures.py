"""Deterministic public and evaluator-only EDIT-1 fixtures."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET

from . import CASE_ID, CASE_VERSION
from .spec import EXPECTED_LINES, PUBLIC_FILE

NS = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
ET.register_namespace("office", NS)
ET.register_namespace("text", TEXT)

INITIAL_LINES = (
    "Release status: STATUS | HOLD-FOR-REVIEW",
    "Reviewer code: ____; fixed-width field",
    "Guard phrase: DO-NOT-ALTER-THIS-LINE",
)


def render_fodt(lines: tuple[str, ...]) -> bytes:
    root = ET.Element(f"{{{NS}}}document", {f"{{{NS}}}mimetype":
                                               "application/vnd.oasis.opendocument.text"})
    body = ET.SubElement(root, f"{{{NS}}}body")
    text = ET.SubElement(body, f"{{{NS}}}text")
    for line in lines:
        para = ET.SubElement(text, f"{{{TEXT}}}p")
        para.text = line
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def build_fixture(root: str | Path) -> dict[str, object]:
    base = Path(root)
    public = base / "public"
    private = base / "private"
    negatives = private / "negative_overwrite_signature"
    for directory in (public, private, negatives):
        directory.mkdir(parents=True, exist_ok=True)
    initial = render_fodt(INITIAL_LINES)
    gold = render_fodt(EXPECTED_LINES)
    overwritten = render_fodt((
        "Release status: STATUS | READY OR-REVIEW",
        EXPECTED_LINES[1], EXPECTED_LINES[2]))
    (public / PUBLIC_FILE).write_bytes(initial)
    (private / "gold.fodt").write_bytes(gold)
    (negatives / "release_notice.fodt").write_bytes(overwritten)
    manifest = {"case_id": CASE_ID, "case_version": CASE_VERSION,
                "files": {"public/" + PUBLIC_FILE: hashlib.sha256(initial).hexdigest(),
                          "private/gold.fodt": hashlib.sha256(gold).hexdigest(),
                          "private/negative_overwrite_signature/release_notice.fodt":
                              hashlib.sha256(overwritten).hexdigest()}}
    (base / "fixture_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
