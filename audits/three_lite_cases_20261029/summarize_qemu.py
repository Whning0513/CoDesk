"""Summarize run-owned QEMU process samples; no other containers are queried."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def summarize(run_root: Path) -> dict:
    path = run_root / "qemu_process_resources.jsonl"
    samples = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    active = [s for s in samples if s["guest_count"]]
    if not active:
        return {"run_id": run_root.name, "samples": len(samples), "guest_count_peak": 0}
    first = active[0]
    last = active[-1]
    cpu_by_container: dict[str, list[float]] = {}
    for sample in active:
        for guest in sample["guests"]:
            cid = guest["container_id"]
            cpu_by_container.setdefault(cid, []).append(float(guest["cpu_seconds"]))
    return {
        "run_id": run_root.name,
        "samples": len(samples),
        "guest_count_peak": max(s["guest_count"] for s in active),
        "sampled_duration_s": round(last["time"] - first["time"], 3),
        "peak_sum_rss_gib": round(max(s["rss_sum_bytes"] for s in active) / 2**30, 3),
        "peak_single_rss_gib": round(max(g["rss_bytes"] for s in active for g in s["guests"]) / 2**30, 3),
        "observed_qemu_cpu_delta_s": round(sum(values[-1] - values[0]
            for values in cpu_by_container.values()), 3),
        "scope": "PID process samples for Docker containers bearing this exact run label; CPU delta excludes boot before first sample and may miss the tail after last sample.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.run_root), indent=2))
