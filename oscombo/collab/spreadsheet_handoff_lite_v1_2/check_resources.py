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
    samples = []
    if samples_path.exists():
        for line in samples_path.read_text().splitlines():
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                pass
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
    return {"run_id": root.name, "requested_profile_ok": profile_ok,
            "qemu_profile_observed": guest_profiles, "expected_initial_guest_count": guest_count,
            "actual_profile_ok": qemu_ok, "host_resource_coverage": host_coverage,
            "resource_observation_complete": bool(profile_ok and qemu_ok and host_coverage)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root", type=Path)
    parser.add_argument("guest_count", type=int, choices=(1, 2))
    args = parser.parse_args()
    result = check(args.run_root, args.guest_count)
    (args.run_root / "resource_profile_check.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["resource_observation_complete"] else 3)
