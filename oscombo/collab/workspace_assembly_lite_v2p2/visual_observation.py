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


def _document_region(png: bytes) -> Image.Image:
    with Image.open(io.BytesIO(png)) as image:
        image.load()
        width, height = image.size
        if image.format != "PNG" or width < 640 or height < 400:
            raise ValueError("unexpected screenshot format or geometry")
        # LibreOffice's current Ubuntu guest puts its application label at the
        # left of the GNOME panel and does not show the document name in a
        # centered title bar.  The document itself is centered on the page.
        # Compare ink in this normalized body region, away from the clock,
        # menus, and sidebars; keep the WM title check as an independent gate.
        return image.convert("RGB").crop(
            (round(width * 0.20), round(height * 0.15),
             round(width * 0.80), round(height * 0.95)))


def _ink_mask(image: Image.Image) -> Image.Image:
    return image.convert("L").point(lambda value: 255 if value < 128 else 0)


def _changed_pixels(reference: Image.Image, candidate: Image.Image) -> int:
    if reference.size != candidate.size:
        raise ValueError("screenshot geometry changed during peer-view capture")
    # Ignore focus recolors and other UI chrome; count changed dark ink in the
    # document body. This reads no task answer and makes no content judgment.
    return ImageChops.difference(_ink_mask(reference), _ink_mask(candidate)).histogram()[255]


def capture_peer_view_candidate(
    guest, run_root: Path, expected_basename: str, baseline_png: bytes,
    *, max_wait_s: float = 45.0, interval_s: float = 2.0,
    max_attempts: int = 12, min_changed_fraction: float = 0.002,
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
    baseline = _document_region(baseline_png)
    baseline_pixels = _ink_mask(baseline).tobytes()
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
        content = _document_region(frame)
        pixels = _ink_mask(content).tobytes()
        changed = _changed_pixels(baseline, content)
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
            "document_region_changed_ink_pixels": changed,
            "document_region_changed_ink_fraction": changed / (baseline.width * baseline.height),
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
        "comparison_region_normalized": [0.20, 0.15, 0.80, 0.95],
        "min_changed_ink_pixels_for_this_geometry": min_changed_pixels,
        "attempts": attempts,
        "scope": "WM title and changed/stable document-region ink are only a visual candidate; "
                 "a human must check the full screenshot for the visible delivered file.",
    }
    if selected:
        title, source = selected
        screenshot = screenshot_dir / "control_B_peer_view.png"
        screenshot.write_bytes(source.read_bytes())
        record["selected_screenshot"] = str(screenshot.relative_to(run_root))
    manifest.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    if not selected:
        raise RuntimeError("B peer-view screenshot did not stabilize a visible document-content change for the expected WM title")
    return title, screenshot, manifest
