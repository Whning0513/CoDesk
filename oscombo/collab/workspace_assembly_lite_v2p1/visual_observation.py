"""Bounded, read-only visual candidate capture for scripted peer-view controls.

An X11 active-window title can change before the screen capture catches up, or
the focused window can remain behind another window.  A changed title-bar
frame is only a candidate for human review, never proof of file contents.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import time

from PIL import Image, ImageChops


def _title_band(png: bytes) -> Image.Image:
    with Image.open(io.BytesIO(png)) as image:
        image.load()
        width, height = image.size
        if image.format != "PNG" or width < 640 or height < 400:
            raise ValueError("unexpected screenshot format or geometry")
        # Exclude the changing GNOME clock and document body.  The centered
        # application title is in this band at every supported Guest size.
        return image.convert("RGB").crop(
            (width // 4, max(24, height // 40), width * 3 // 4, max(65, height * 7 // 100)))


def _changed_pixels(reference: Image.Image, candidate: Image.Image) -> int:
    if reference.size != candidate.size:
        raise ValueError("screenshot geometry changed during peer-view capture")
    # Compare the shape of dark title text, not raw RGB.  A report window can
    # change focus color without changing its visible title; the first v2.1
    # control showed 1308 raw changed pixels but only 121 changed ink pixels
    # while it still displayed the old report.  This reads no task answer.
    first = reference.convert("L").point(lambda value: 255 if value < 128 else 0)
    second = candidate.convert("L").point(lambda value: 255 if value < 128 else 0)
    return ImageChops.difference(first, second).histogram()[255]


def capture_peer_view_candidate(
    guest, run_root: Path, expected_basename: str, baseline_png: bytes,
    *, max_wait_s: float = 45.0, interval_s: float = 2.0,
    max_attempts: int = 12, min_changed_fraction: float = 0.01,
) -> tuple[str, Path, Path]:
    """Return a stable visual candidate and WM title, or fail with all attempts retained.

    The caller must visually inspect the saved PNG before treating the control
    as evidence that B saw the correct file.  This function never sends GUI
    input, reads the note, or changes the task/scorer.
    """
    if not expected_basename or max_wait_s <= 0 or max_attempts < 2 or not 0 < min_changed_fraction < 1:
        raise ValueError("invalid peer-view capture bounds")
    run_root = Path(run_root)
    screenshot_dir = run_root / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    baseline_path = screenshot_dir / "control_B_peer_view_before.png"
    baseline_path.write_bytes(baseline_png)
    baseline = _title_band(baseline_png)
    baseline_pixels = baseline.tobytes()
    min_changed_pixels = max(1, round(baseline.width * baseline.height * min_changed_fraction))
    deadline = time.monotonic() + max_wait_s
    attempts: list[dict] = []
    previous_candidate: bytes | None = None
    stable_count = 0
    selected: tuple[str, Path] | None = None
    expected = expected_basename.casefold()
    for number in range(1, max_attempts + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        before = guest.active_window() or ""
        frame = guest.screenshot(patience=min(45.0, remaining))
        after = guest.active_window() or ""
        image_path = screenshot_dir / f"control_B_peer_view_attempt_{number:02d}.png"
        image_path.write_bytes(frame)
        band = _title_band(frame)
        pixels = band.tobytes()
        changed = _changed_pixels(baseline, band)
        title_matches = all(expected in title.casefold() and "read-only" in title.casefold()
                            for title in (before, after))
        visual_change = pixels != baseline_pixels and changed >= min_changed_pixels
        if title_matches and visual_change:
            stable_count = stable_count + 1 if pixels == previous_candidate else 1
            previous_candidate = pixels
        else:
            stable_count = 0
            previous_candidate = None
        attempts.append({
            "number": number, "before_window": before, "after_window": after,
            "screenshot": str(image_path.relative_to(run_root)),
            "screenshot_sha256": hashlib.sha256(frame).hexdigest(),
            "title_band_changed_pixels": changed,
            "wm_title_matches": title_matches,
            "visual_change_candidate": visual_change,
            "stable_candidate_frames": stable_count,
            "sampled_at": time.time(),
        })
        if stable_count >= 2:
            selected = (after, image_path)
            break
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(interval_s, remaining))
    manifest = run_root / "control_B_peer_view_observation.json"
    record = {
        "status": "candidate_pending_manual_review" if selected else "visual_frame_unverified",
        "expected_basename": expected_basename,
        "baseline_screenshot": str(baseline_path.relative_to(run_root)),
        "max_wait_s": max_wait_s,
        "max_attempts": max_attempts,
        "min_changed_fraction": min_changed_fraction,
        "min_changed_pixels_for_this_geometry": min_changed_pixels,
        "attempts": attempts,
        "scope": "WM title and changed/stable title-band pixels are only a visual candidate; "
                 "a human must check the full screenshot for the visible delivered file.",
    }
    if selected:
        title, source = selected
        screenshot = screenshot_dir / "control_B_peer_view.png"
        screenshot.write_bytes(source.read_bytes())
        record["selected_screenshot"] = str(screenshot.relative_to(run_root))
    manifest.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    if not selected:
        raise RuntimeError("B peer-view visual frame did not stabilize with the expected WM title")
    return title, screenshot, manifest
