"""Read-only per-run QEMU RSS and CPU sampler for rootless Docker Guests."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time


def _docker(*args: str) -> str:
    completed = subprocess.run(("docker", *args), capture_output=True, text=True,
                               timeout=15, check=True)
    return completed.stdout.strip()


def _process_usage(pid: int) -> dict | None:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1].split()
        resident_pages = int(Path(f"/proc/{pid}/statm").read_text().split()[1])
        return {"rss_bytes": resident_pages * os.sysconf("SC_PAGE_SIZE"),
                "cpu_seconds": (int(stat[11]) + int(stat[12])) / os.sysconf("SC_CLK_TCK")}
    except (FileNotFoundError, IndexError, ValueError):
        return None


def sample(run_root: Path, interval_s: float, max_seconds: float) -> None:
    run_root = run_root.resolve()
    run_id = run_root.name
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", run_id):
        raise ValueError("unsafe run_id")
    if not run_root.is_dir():
        raise FileNotFoundError(run_root)
    output = run_root / "qemu_process_resources.jsonl"
    started = time.monotonic()
    seen = False
    while time.monotonic() - started < max_seconds:
        ids = _docker("ps", "-q", "--filter", f"label=oscombo.run={run_id}").splitlines()
        seen = seen or bool(ids)
        samples = []
        for container_id in ids:
            full_id, pid_text = _docker("inspect", "--format",
                                         "{{.Id}} {{.State.Pid}}", container_id).split()
            pid = int(pid_text)
            usage = _process_usage(pid)
            if usage:
                samples.append({"container_id": full_id, "pid": pid, **usage})
        record = {"run_id": run_id, "time": time.time(), "guests": samples,
                  "guest_count": len(samples),
                  "rss_sum_bytes": sum(item["rss_bytes"] for item in samples),
                  "cpu_seconds_sum": sum(item["cpu_seconds"] for item in samples)}
        with output.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        if seen and not ids and ((run_root / "result.json").exists()
                                 or (run_root / "failure.json").exists()):
            return
        time.sleep(interval_s)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root", type=Path)
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--max-seconds", type=float, default=3600)
    args = parser.parse_args()
    sample(args.run_root, args.interval, args.max_seconds)
