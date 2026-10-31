"""Run one read-only Guest screenshot acquisition in a killable helper process.

The parent enforces the overall deadline, including process startup and a
slow-dripping response. This helper never issues GUI input or reads secrets.
"""
from __future__ import annotations

import sys
import time

import requests


def _valid_image(content_type: str, data: bytes) -> bool:
    # Match the OSWorld controller's accepted image response semantics.
    return bool(data and (data.startswith(b"\x89PNG\r\n\x1a\n") or data.startswith(b"\xff\xd8\xff")
                          or any(t in content_type.lower() for t in ("image/png", "image/jpeg", "image/jpg"))))


def main() -> int:
    url, duration = sys.argv[1], float(sys.argv[2])
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            response = requests.get(url.rstrip("/") + "/screenshot", timeout=(min(5, remaining), min(120, remaining)))
            if response.status_code == 200 and _valid_image(response.headers.get("Content-Type", ""), response.content):
                sys.stdout.buffer.write(response.content)
                sys.stdout.buffer.flush()
                return 0
        except requests.RequestException:
            pass
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(5, remaining))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
