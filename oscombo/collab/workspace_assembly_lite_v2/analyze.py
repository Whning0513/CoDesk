"""Compute timing, usage and lock metrics from recorded v2 model runs."""
from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path


def rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def merge(intervals):
    merged = []
    for start, end in sorted((float(a), float(b)) for a, b in intervals if a is not None and b is not None and b > a):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def overlap(first, second):
    a, b = merge(first), merge(second)
    total, i, j = 0.0, 0, 0
    while i < len(a) and j < len(b):
        total += max(0.0, min(a[i][1], b[j][1]) - max(a[i][0], b[j][0]))
        if a[i][1] <= b[j][1]: i += 1
        else: j += 1
    return round(total, 3)


def subtract(base, cuts):
    pieces = list(base)
    for start, end in merge(cuts):
        next_pieces = []
        for left, right in pieces:
            if end <= left or start >= right:
                next_pieces.append((left, right))
            else:
                if left < start: next_pieces.append((left, start))
                if end < right: next_pieces.append((end, right))
        pieces = next_pieces
    return pieces


def analyze(root: Path) -> dict:
    meta = json.loads((root / "provenance.json").read_text())
    result = json.loads((root / "result.json").read_text())
    actors = {row["actor"]: row for row in rows(root / "actors.jsonl") if row.get("actor") in {"A", "B"}}
    if set(actors) != {"A", "B"}:
        raise ValueError("both Actor timing records are required")
    relay = rows(root / "codex_relay_events.jsonl")
    lifecycle = rows(root / "actor_lifecycle.jsonl")
    active, waits, errors, metrics, requests, inputs = {}, {}, [], {}, {}, {}
    for role in "AB":
        actor = actors[role]
        start, end = float(actor["started_at"]), float(actor["ended_at"])
        role_events = sorted((e for e in lifecycle if e.get("actor") == role), key=lambda x: x.get("time", 0))
        pending, cuts = None, []
        for event in role_events:
            kind, stamp = event.get("event"), float(event.get("time", 0))
            if kind == "suspended_for_peer_handoff":
                if pending is not None: errors.append(f"{role}: overlapping suspension")
                else: pending = max(start, stamp)
            elif kind in {"woken_by_peer_handoff", "peer_handoff_wait_expired", "peer_finished_without_handoff"}:
                if pending is None: errors.append(f"{role}: terminal wait event without suspension")
                else:
                    cuts.append((pending, min(end, stamp)))
                    pending = None
        if pending is not None:
            cuts.append((pending, end))
            errors.append(f"{role}: suspension has no terminal event")
        waits[role] = round(sum(max(0.0, b - a) for a, b in merge(cuts)), 3)
        active[role] = subtract([(start, end)], cuts)
        actions = rows(root / f"actor_runs/{role}/{role}/actions.jsonl")
        req = [r for r in relay if r.get("actor") == role]
        requests[role] = [(r.get("started_at"), r.get("time")) for r in req]
        inputs[role] = [(a.get("action_started_at"), a.get("action_ended_at"))
                        for a in actions if a.get("executed")]
        executed = [a for a in actions if a.get("executed")]
        locks = [a.get("input_lock") or {} for a in executed]
        usage = [r.get("usage") or {} for r in req if r.get("upstream_status") == 200]
        metrics[role] = {"status": actor.get("status"), "desktop_calls": len(actions),
            "executed_inputs": len(executed), "gui_input_s": round(sum(b-a for a,b in merge(inputs[role])), 3),
            "screenshot_s": round(sum(float(a.get("screenshot_s") or 0) for a in actions), 3),
            "model_requests": len(req), "model_request_s": round(sum(float(r.get("elapsed_s") or 0) for r in req), 3),
            "http_statuses": dict(Counter(str(r.get("upstream_status")) for r in req)),
            "input_tokens": sum(u.get("input_tokens", 0) for u in usage),
            "output_tokens": sum(u.get("output_tokens", 0) for u in usage),
            "cached_input_tokens": sum((u.get("input_tokens_details") or {}).get("cached_tokens", 0) for u in usage),
            "total_tokens": sum(u.get("total_tokens", 0) for u in usage),
            "locked_inputs": sum(bool(lock.get("enabled")) for lock in locks),
            "lock_wait_s": round(sum(float(lock.get("wait_s") or 0) for lock in locks), 6),
            "lock_held_s": round(sum(float(lock.get("held_s") or 0) for lock in locks), 6)}
    samples = rows(root / "resource_samples_v2.jsonl")
    qemu = defaultdict(list)
    for sample in samples:
        for item in sample.get("guests", []):
            qemu[(item["container_id"], item["pid"], item["process_created"])].append(item["cpu_seconds"])
    def used_swap(sample):
        info = sample.get("host_meminfo", {})
        try: return (int(info["SwapTotal"].split()[0]) - int(info["SwapFree"].split()[0])) * 1024
        except (KeyError, ValueError, IndexError): return None
    swap = [x for x in map(used_swap, samples) if x is not None]
    first_actor = min(float(a["started_at"]) for a in actors.values())
    last_actor = max(float(a["ended_at"]) for a in actors.values())
    setup = first_actor - float(meta["started_at"])
    total = float(result["elapsed_s"])
    actor_phase = last_actor - first_actor
    return {"run_id": root.name, "status": result["status"], "actors": metrics,
        "artifact_oracle": result["oracle"], "behavioral_audit": result.get("behavioral_audit"),
        "setup_s": round(setup, 3), "actor_phase_s": round(actor_phase, 3),
        "post_actor_s": round(max(0, total - setup - actor_phase), 3), "total_s": total,
        "suspended_wait_s": waits, "active_overlap_s": overlap(active["A"], active["B"]),
        "gui_input_overlap_s": overlap(inputs["A"], inputs["B"]),
        "model_request_overlap_s": overlap(requests["A"], requests["B"]),
        "lifecycle_errors": errors,
        "qemu_sampled_cpu_delta_s": round(sum(max(v) - min(v) for v in qemu.values()), 3),
        "qemu_peak_sum_rss_bytes": max((sum(g.get("rss_bytes", 0) for g in s.get("guests", [])) for s in samples), default=0),
        "host_peak_swap_used_bytes": max(swap) if swap else None,
        "min_disk_available_bytes": min((s["disk_available_bytes"] for s in samples), default=None),
        "resource_scope": "QEMU CPU/RSS and host swap/disk/IO are sampled; IO pressure and per-process bytes remain in raw samples."}


if __name__ == "__main__":
    import sys
    root = Path(sys.argv[1]).resolve()
    data = analyze(root)
    (root / "model_metrics_v2.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"run_id": root.name, "active_overlap_s": data["active_overlap_s"]}))
