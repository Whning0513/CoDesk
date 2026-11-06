"""Peer-view capture follows Writer's visible page, not a centered title bar."""
from __future__ import annotations

import io
import json

from PIL import Image, ImageDraw
import pytest

from oscombo.collab.workspace_assembly_lite_v2p2.visual_observation import capture_peer_view_candidate


NOTE_TITLE = "inspection_note-r000001.txt (read-only) - LibreOffice Writer"
REPORT_TITLE = "handoff_report.odt - LibreOffice Writer"


def _frame(*, document: str, focused: bool = False, caret: bool = False) -> bytes:
    """Simulate the current guest: left app label, no centered file title."""
    image = Image.new("RGB", (1920, 1080), "#eeeeee")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1919, 27), fill="#333333" if not focused else "#777777")
    draw.rectangle((560, 183, 1356, 1055), fill="white")
    # The GNOME app label stays at the left and is identical across documents.
    draw.text((118, 7), "LibreOffice Writer", fill="white" if not focused else "#eeeeee")
    lines = ([315, 260, 220, 140] if document == "report" else [265, 180, 125])
    y = 370 if document == "report" else 260
    for width in lines:
        draw.rectangle((638, y, 638 + width, y + 5), fill="#111111")
        y += 24
    if caret:
        draw.rectangle((905, 259, 907, 280), fill="#111111")
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


class Guest:
    def __init__(self, frames: list[bytes], title: str = NOTE_TITLE):
        self.frames = iter(frames)
        self.title = title

    def active_window(self) -> str:
        return self.title

    def screenshot(self, patience: float) -> bytes:
        return next(self.frames)


def test_left_positioned_app_label_and_changed_document_body_stabilize(tmp_path):
    report = _frame(document="report")
    note = _frame(document="note")
    # A transient caret in the first frame must not prevent a later stable
    # pair from being selected.
    guest = Guest([_frame(document="note", caret=True), note, note])

    title, shot, manifest = capture_peer_view_candidate(
        guest, tmp_path, "inspection_note-r000001.txt", report,
        max_wait_s=5, interval_s=0, max_attempts=3)

    data = json.loads(manifest.read_text())
    assert title == NOTE_TITLE and shot.read_bytes() == note
    assert data["status"] == "candidate_pending_manual_review"
    assert data["comparison_region_normalized"] == [0.20, 0.15, 0.80, 0.95]
    assert [row["stable_candidate_frames"] for row in data["attempts"]] == [1, 1, 2]
    assert all(row["wm_title_matches"] for row in data["attempts"])
    assert all(row["document_region_changed_ink_pixels"] >= data["min_changed_ink_pixels_for_this_geometry"]
               for row in data["attempts"])
    assert "human must check the full screenshot" in data["scope"]


def test_expected_wm_title_without_visible_document_change_fails_closed(tmp_path):
    report = _frame(document="report")
    guest = Guest([report, report])

    with pytest.raises(RuntimeError, match="document-content change"):
        capture_peer_view_candidate(guest, tmp_path, "inspection_note-r000001.txt", report,
                                    max_wait_s=5, interval_s=0, max_attempts=2)

    data = json.loads((tmp_path / "control_B_peer_view_observation.json").read_text())
    assert data["status"] == "visual_frame_unverified"
    assert all(row["wm_title_matches"] for row in data["attempts"])
    assert all(row["document_region_changed_ink_pixels"] == 0 for row in data["attempts"])
    assert not (tmp_path / "screenshots/control_B_peer_view.png").exists()


def test_toolbar_or_focus_recolor_does_not_count_as_document_change(tmp_path):
    report = _frame(document="report")
    focused = _frame(document="report", focused=True)
    guest = Guest([focused, focused])

    with pytest.raises(RuntimeError, match="document-content change"):
        capture_peer_view_candidate(guest, tmp_path, "inspection_note-r000001.txt", report,
                                    max_wait_s=5, interval_s=0, max_attempts=2)

    data = json.loads((tmp_path / "control_B_peer_view_observation.json").read_text())
    assert all(row["document_region_changed_ink_pixels"] == 0 for row in data["attempts"])


def test_document_change_with_wrong_wm_title_fails_closed(tmp_path):
    report, note = _frame(document="report"), _frame(document="note")
    guest = Guest([note, note], title=REPORT_TITLE)

    with pytest.raises(RuntimeError, match="document-content change"):
        capture_peer_view_candidate(guest, tmp_path, "inspection_note-r000001.txt", report,
                                    max_wait_s=5, interval_s=0, max_attempts=2)

    data = json.loads((tmp_path / "control_B_peer_view_observation.json").read_text())
    assert all(not row["wm_title_matches"] for row in data["attempts"])
    assert all(row["visual_change_candidate"] for row in data["attempts"])
