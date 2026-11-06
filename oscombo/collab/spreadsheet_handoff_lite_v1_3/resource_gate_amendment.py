"""Offline draft of a versioned capacity policy for a read-only Guest base.

This helper is deliberately not imported by the frozen v1.3 runner. A future
protocol amendment may use it after review. Writable run resources retain the
existing capacity gate; the immutable qcow2 base is verified by digest and by
the actual Docker mount record instead of requiring free space on its device.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
from typing import Any


MIN_FREE_BYTES = 15 * 1024**3
MIN_FREE_INODES = 1024
BASE_DESTINATION = "/System.qcow2"


def writable_path_errors(path: str | Path, *, available_bytes: int,
                         available_inodes: int,
                         min_free_bytes: int = MIN_FREE_BYTES,
                         min_free_inodes: int = MIN_FREE_INODES) -> list[str]:
    """Apply the fail-closed free-space gate only to a writable directory."""
    candidate = Path(path)
    errors: list[str] = []
    try:
        resolved = candidate.resolve(strict=True)
        if not resolved.is_dir():
            errors.append("not a directory")
        if not os.access(resolved, os.W_OK | os.X_OK):
            errors.append("not writable/searchable")
    except OSError:
        return ["path unavailable"]
    if available_bytes < min_free_bytes:
        errors.append("below minimum free bytes")
    if available_inodes < min_free_inodes:
        errors.append("below minimum free inodes")
    return errors


def image_fingerprint(image_path: str | Path) -> dict[str, int]:
    """Return stable metadata used to detect ordinary changes during a run."""
    image = Path(image_path)
    if image.is_symlink():
        raise ValueError("Guest base image path must not be a symbolic link")
    resolved = image.resolve(strict=True)
    if not resolved.is_file() or not os.access(resolved, os.R_OK):
        raise ValueError("Guest base image must be a readable regular file")
    stat = resolved.stat()
    return {"device": stat.st_dev, "inode": stat.st_ino, "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns}


def verify_frozen_image_sha256(image_path: str | Path,
                              expected_sha256: str) -> dict[str, int]:
    """Hash the immutable base once before boot and compare with the freeze."""
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("frozen Guest image SHA-256 is missing or malformed")
    image = Path(image_path)
    before = image_fingerprint(image)
    digest = hashlib.sha256()
    with image.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    after = image_fingerprint(image)
    if before != after:
        raise ValueError("Guest base image changed while it was being hashed")
    if digest.hexdigest() != expected_sha256:
        raise ValueError("Guest base image does not match the frozen SHA-256")
    return after


def _inside(path: str | Path, parent: str | Path) -> bool:
    try:
        Path(path).resolve(strict=True).relative_to(Path(parent).resolve(strict=True))
        return True
    except (OSError, ValueError):
        return False


def verify_guest_mount_and_writes(*, image_path: str | Path,
                                  run_root: str | Path,
                                  mount: dict[str, Any] | None,
                                  overlay_path: str | Path,
                                  cache_path: str | Path) -> None:
    """Require the exact RO image mount and run-owned writable paths."""
    if not isinstance(mount, dict):
        raise ValueError("Guest base mount evidence is missing")
    image = str(Path(image_path).resolve(strict=True))
    source = mount.get("Source")
    if not isinstance(source, str):
        raise ValueError("Guest base mount source is missing")
    try:
        source = str(Path(source).resolve(strict=True))
    except OSError as exc:
        raise ValueError("Guest base mount source is unavailable") from exc
    if mount.get("Destination") != BASE_DESTINATION or source != image or mount.get("RW") is not False:
        raise ValueError("Guest base must be the exact read-only /System.qcow2 mount")
    overlay_root = Path(run_root).resolve(strict=True) / "overlay"
    cache_root = Path(run_root).resolve(strict=True) / "cache"
    if not _inside(overlay_path, overlay_root):
        raise ValueError("Guest overlay must be inside this run's overlay directory")
    if not _inside(cache_path, cache_root):
        raise ValueError("Guest cache must be inside this run's cache directory")


def verify_image_unchanged(image_path: str | Path,
                           frozen_fingerprint: dict[str, int]) -> None:
    """Check post-run metadata without rescanning a large image a second time."""
    if image_fingerprint(image_path) != frozen_fingerprint:
        raise ValueError("Guest base image metadata changed during the run")
