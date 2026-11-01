"""A bounded inotify headroom probe; it releases every temporary watch."""
from __future__ import annotations

import ctypes
import errno
import json
import os
from pathlib import Path
import tempfile


def probe(count: int = 64) -> dict:
    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.inotify_init1(os.O_CLOEXEC)
    if fd < 0:
        return {"requested": count, "allocated": 0, "errno": ctypes.get_errno()}
    allocated, error = 0, 0
    try:
        with tempfile.TemporaryDirectory(prefix="codesk-watch-probe-") as root:
            for index in range(count):
                path = Path(root) / str(index)
                path.mkdir()
                if libc.inotify_add_watch(fd, os.fsencode(path), 0x100) < 0:
                    error = ctypes.get_errno()
                    break
                allocated += 1
    finally:
        os.close(fd)
    return {"requested": count, "allocated": allocated, "errno": error,
            "errno_name": errno.errorcode.get(error) if error else None}


if __name__ == "__main__":
    result = probe()
    print(json.dumps(result))
    raise SystemExit(0 if result["allocated"] == result["requested"] else 3)
