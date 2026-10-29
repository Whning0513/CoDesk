"""Public attachment and Writer file for a one-asset handoff."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from oscombo.collab.data_to_deck.fixtures import NS, _manifest_xml, _write_odf
from . import spec


def asset_text() -> str:
    return "Inspection note for the Aurora supply review.\nInspection tag: RIVER-27.\nStatus: current.\n"


def draft_text() -> str:
    return "Aurora Supply Handoff\nThe delivered inspection attachment is [await A file and tag].\nPrepared for operations review."


def report_odt(path: Path, sentence: str | None = None) -> None:
    text_ns = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
    lines = draft_text().splitlines()
    if sentence is not None:
        lines[1] = sentence
    body = "".join(f"<text:p>{line}</text:p>" for line in lines)
    content = (f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="{NS['office']}" xmlns:text="{text_ns}" office:version="1.2">
<office:body><office:text>{body}</office:text></office:body></office:document-content>''').encode()
    styles = (f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles xmlns:office="{NS['office']}" xmlns:style="{NS['style']}" office:version="1.2">
<office:styles><style:default-style style:family="paragraph"/></office:styles>
<office:automatic-styles/><office:master-styles/></office:document-styles>''').encode()
    mimetype = "application/vnd.oasis.opendocument.text"
    _write_odf(path, mimetype, {"content.xml": content, "styles.xml": styles,
                              "meta.xml": (f'''<?xml version="1.0"?><office:document-meta xmlns:office="{NS['office']}" office:version="1.2"><office:meta/></office:document-meta>''').encode(),
                              "settings.xml": (f'''<?xml version="1.0"?><office:document-settings xmlns:office="{NS['office']}" office:version="1.2"><office:settings/></office:document-settings>''').encode(),
                              "META-INF/manifest.xml": _manifest_xml(mimetype, "content.xml")})


def build_fixture(root: str | Path) -> dict:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise FileExistsError(f"Lite fixture destination is not empty: {root}")
    (root / spec.FIXTURE_NAMES["asset"]).write_text(asset_text(), encoding="utf-8")
    report_odt(root / spec.FIXTURE_NAMES["report"])
    (root / spec.FIXTURE_NAMES["brief"]).write_text(
        "Move the one incoming inspection note through File Manager, preserving its content. "
        "A shares the delivered path and inspection tag. B uses the delivered file to finish the Writer report. "
        "The report is already open; B can prepare while A works. Both roles save and publish outputs.\n",
        encoding="utf-8")
    files = {name: {"sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(),
                    "bytes": (root / name).stat().st_size}
             for name in spec.FIXTURE_NAMES.values()}
    manifest = {"case_id": spec.CASE_ID, "case_version": spec.CASE_VERSION,
                "fixture_sha256": files, "conditions": spec.CONDITIONS,
                "outputs": spec.OUTPUTS, "role_budgets": spec.ROLE_BUDGET}
    (root / "fixture_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
