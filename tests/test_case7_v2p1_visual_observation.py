"""The scripted control must not equate an X11 title with a visible frame."""
from __future__ import annotations

import io
import json

from PIL import Image, ImageDraw
import pytest

from oscombo.collab.workspace_assembly_lite_v2p1.visual_observation import capture_peer_view_candidate


NOTE_TITLE = "inspection_note-r000001.txt (read-only) - LibreOffice Writer"
REPORT_TITLE = "handoff_report.odt - LibreOffice Writer"


def _frame(*, changed: bool) -> bytes:
    image = Image.new("RGB", (1280, 720), "white")
    if changed:
        ImageDraw.Draw(image).rectangle((500, 30, 780, 48), fill="black")
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


class Guest:
    def __init__(self, frames: list[bytes], title: str = NOTE_TITLE):
        self.frames = iter(frames)
        self.title = title
        self.patiences: list[float] = []

    def active_window(self) -> str:
        return self.title

    def screenshot(self, patience: float) -> bytes:
        self.patiences.append(patience)
        return next(self.frames)


def test_waits_past_stale_report_frame_and_retains_visual_candidate(tmp_path):
    report, note = _frame(changed=False), _frame(changed=True)
    guest = Guest([report, note, note])
    title, shot, manifest = capture_peer_view_candidate(
        guest, tmp_path, "inspection_note-r000001.txt", report,
        max_wait_s=5, interval_s=0, max_attempts=3)
    data = json.loads(manifest.read_text())
    assert title == NOTE_TITLE and shot.read_bytes() == note
    assert data["status"] == "candidate_pending_manual_review"
    assert [row["stable_candidate_frames"] for row in data["attempts"]] == [0, 1, 2]
    assert all(row["wm_title_matches"] for row in data["attempts"])
    assert data["scope"].endswith("visible delivered file.")
    assert len(guest.patiences) == 3


def test_matching_window_title_with_unchanged_screen_fails_closed(tmp_path):
    report = _frame(changed=False)
    guest = Guest([report, report, report])
    with pytest.raises(RuntimeError, match="visual frame did not stabilize"):
        capture_peer_view_candidate(guest, tmp_path, "inspection_note-r000001.txt", report,
                                    max_wait_s=5, interval_s=0, max_attempts=3)
    data = json.loads((tmp_path / "control_B_peer_view_observation.json").read_text())
    assert data["status"] == "visual_frame_unverified"
    assert not (tmp_path / "screenshots/control_B_peer_view.png").exists()
    assert len(data["attempts"]) == 3


def test_changed_screen_with_wrong_window_title_fails_closed(tmp_path):
    report, note = _frame(changed=False), _frame(changed=True)
    guest = Guest([note, note], title=REPORT_TITLE)
    with pytest.raises(RuntimeError, match="visual frame did not stabilize"):
        capture_peer_view_candidate(guest, tmp_path, "inspection_note-r000001.txt", report,
                                    max_wait_s=5, interval_s=0, max_attempts=2)
    data = json.loads((tmp_path / "control_B_peer_view_observation.json").read_text())
    assert all(not row["wm_title_matches"] for row in data["attempts"])


def test_focus_recolor_alone_is_not_a_new_visible_title(tmp_path):
    baseline = Image.new("RGB", (1280, 720), "white")
    ImageDraw.Draw(baseline).rectangle((540, 32, 740, 48), fill=(40, 40, 40))
    recolored = Image.new("RGB", (1280, 720), (225, 225, 225))
    ImageDraw.Draw(recolored).rectangle((540, 32, 740, 48), fill=(75, 75, 75))
    def png(image):
        out = io.BytesIO()
        image.save(out, format="PNG")
        return out.getvalue()
    original, focused = png(baseline), png(recolored)
    guest = Guest([focused, focused])
    with pytest.raises(RuntimeError, match="visual frame did not stabilize"):
        capture_peer_view_candidate(guest, tmp_path, "inspection_note-r000001.txt", original,
                                    max_wait_s=5, interval_s=0, max_attempts=2)
    data = json.loads((tmp_path / "control_B_peer_view_observation.json").read_text())
    assert all(row["title_band_changed_pixels"] == 0 for row in data["attempts"])
