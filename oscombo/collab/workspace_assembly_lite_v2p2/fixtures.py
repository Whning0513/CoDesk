"""Independent short-code note and Writer form for v2.2."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from xml.sax.saxutils import escape

from oscombo.collab.data_to_deck.fixtures import NS, _manifest_xml, _write_odf
from . import spec

DEFAULT_TAG = "682"


def tag_for_seed(seed: str) -> str:
    if not isinstance(seed, str) or not seed or len(seed) > 128:
        raise ValueError("fixture seed must be a nonempty string of at most 128 characters")
    digest = hashlib.sha256(("codesk-wa-v2p2:" + seed).encode("utf-8")).digest()
    return "".join(str(2 + (byte % 8)) for byte in digest[:3])


def wrong_code(code: str) -> str:
    """A deterministic negative distinct from every valid three-digit code."""
    if not re.fullmatch(r"[2-9]{3}", code):
        raise ValueError("invalid inspection code")
    return "222" if code != "222" else "333"


def asset_text(tag: str = DEFAULT_TAG) -> str:
    if not re.fullmatch(r"[2-9]{3}", tag):
        raise ValueError("invalid public inspection code")
    return f"Inspection note for the Aurora supply review.\nInspection code: {tag}.\nStatus: current.\n"


def draft_text() -> str:
    return "Aurora Supply Handoff\nPrepared for operations review.\nSource: inspection_note.txt\nAudience:\nInspection code:\n"


def report_odt(path: Path, review: str | None = None, attachment: str | None = None) -> None:
    lines = draft_text().splitlines()
    if review is not None:
        lines[3] = review
    if attachment is not None:
        lines[4] = attachment
    body = "".join(f"<text:p>{escape(line)}</text:p>" for line in lines)
    content = (f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="{NS['office']}" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" office:version="1.2"><office:body><office:text>{body}</office:text></office:body></office:document-content>''').encode()
    styles = (f'''<?xml version="1.0" encoding="UTF-8"?><office:document-styles xmlns:office="{NS['office']}" xmlns:style="{NS['style']}" office:version="1.2"><office:styles><style:default-style style:family="paragraph"/></office:styles><office:automatic-styles/><office:master-styles/></office:document-styles>''').encode()
    mimetype = "application/vnd.oasis.opendocument.text"
    _write_odf(path, mimetype, {"content.xml": content, "styles.xml": styles,
        "meta.xml": (f'''<?xml version="1.0"?><office:document-meta xmlns:office="{NS['office']}" office:version="1.2"><office:meta/></office:document-meta>''').encode(),
        "settings.xml": (f'''<?xml version="1.0"?><office:document-settings xmlns:office="{NS['office']}" office:version="1.2"><office:settings/></office:document-settings>''').encode(),
        "META-INF/manifest.xml": _manifest_xml(mimetype, "content.xml")})


def build_fixture(root: str | Path, inspection_tag: str = DEFAULT_TAG, *, seed: str | None = None) -> dict:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise FileExistsError(f"Lite fixture destination is not empty: {root}")
    selected_tag = tag_for_seed(seed) if seed is not None else inspection_tag
    (root / spec.FIXTURE_NAMES["asset"]).write_text(asset_text(selected_tag), encoding="utf-8")
    report_odt(root / spec.FIXTURE_NAMES["report"])
    (root / spec.FIXTURE_NAMES["brief"]).write_text(
        "A moves the incoming inspection note into the delivery folder and publishes it. "
        "B fills the audience value while A works, then reads the delivered read-only revision in a GUI "
        "and fills only the three-digit inspection code in the separate Writer field.\n",
        encoding="utf-8")
    files = {name: {"sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(),
                    "bytes": (root / name).stat().st_size} for name in spec.FIXTURE_NAMES.values()}
    manifest = {"case_id": spec.CASE_ID, "case_version": spec.CASE_VERSION,
                "fixture_sha256": files, "conditions": spec.CONDITIONS,
                "outputs": spec.OUTPUTS, "role_budgets": spec.ROLE_BUDGET}
    (root / "fixture_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
