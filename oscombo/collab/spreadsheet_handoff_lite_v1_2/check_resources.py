"""Validate that run-scoped resource sampling recorded the frozen Guest profile."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path


def check(root: Path, guest_count: int) -> dict:
    profile_path = root / "resource_profile.json"
    samples_path = root / "resource_samples.jsonl"
    profile = json.loads(profile_path.read_text()) if profile_path.exists() else {}
    provenance_path, result_path = root / "provenance.json", root / "result.json"
    provenance = json.loads(provenance_path.read_text()) if provenance_path.exists() else {}
    result = json.loads(result_path.read_text()) if result_path.exists() else {}
    samples, malformed = [], 0
    if samples_path.exists():
        for line in samples_path.read_text().splitlines():
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    samples.append(value)
                else:
                    malformed += 1
            except json.JSONDecodeError:
                malformed += 1
    guest_profiles = {}
    for sample in samples:
        for guest in sample.get("guests", []):
            guest_profiles[guest.get("container_id")] = guest.get("qemu_config") or {}
    def valid_config(config):
        cpus = str(config.get("cpus") or "").split(",", 1)[0]
        mem = str(config.get("memory") or "").upper().split(",", 1)[0]
        return cpus == "8" and mem in {"8G", "8192M", "8192"}
    host_coverage = bool(samples) and all(
        x.get("host", {}).get("disk_available_bytes") is not None
        and x.get("host", {}).get("diskstats")
        and x.get("host", {}).get("cpu_stat")
        and all(k in x.get("host", {}).get("memory", {})
                for k in ("MemTotal_bytes", "MemAvailable_bytes", "SwapTotal_bytes", "SwapFree_bytes"))
        for x in samples)
    profile_ok = profile.get("requested_guest_cpus") == "8" and profile.get("requested_guest_ram") == "8G"
    qemu_ok = (len(guest_profiles) >= guest_count
               and all(valid_config(config) for config in guest_profiles.values()))
    times = [x.get("time") for x in samples if type(x.get("time")) in (int, float)]
    start, elapsed = provenance.get("started_at"), result.get("elapsed_s")
    interval = profile.get("sample_interval_s", 5)
    cadence_ok = (len(times) == len(samples) and len(times) >= 2 and times == sorted(times)
                  and all(b - a <= max(60, 5 * interval) for a, b in zip(times, times[1:])))
    span_ok = (type(start) in (int, float) and type(elapsed) in (int, float) and elapsed > 0
               and bool(times) and times[0] <= start + 60
               and times[-1] >= start + elapsed - max(30, 4 * interval))
    return {"run_id": root.name, "requested_profile_ok": profile_ok,
            "qemu_profile_observed": guest_profiles, "expected_initial_guest_count": guest_count,
            "actual_profile_ok": qemu_ok, "host_resource_coverage": host_coverage,
            "sample_cadence_ok": cadence_ok, "sample_time_span_ok": span_ok,
            "malformed_sample_lines": malformed,
            "resource_observation_complete": bool(profile_ok and qemu_ok and host_coverage
                                                   and cadence_ok and span_ok and not malformed)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root", type=Path)
    parser.add_argument("guest_count", type=int, choices=(1, 2))
    args = parser.parse_args()
    result = check(args.run_root, args.guest_count)
    (args.run_root / "resource_profile_check.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["resource_observation_complete"] else 3)
