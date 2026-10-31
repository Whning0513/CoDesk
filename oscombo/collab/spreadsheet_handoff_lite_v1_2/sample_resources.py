"""Read-only run-scoped QEMU plus host resource sampler; no process mutations."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path


def _qemu_config(argv: list[str]) -> dict:
    def option(name):
        try:
            return argv[argv.index(name) + 1]
        except (ValueError, IndexError):
            return None
    return {"cpus": option("-smp"), "memory": option("-m")}


def _host_snapshot(run_root: Path) -> dict:
    info = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, _, value = line.partition(":")
        if key in {"MemAvailable", "MemTotal", "SwapTotal", "SwapFree"}:
            info[key + "_bytes"] = int(value.split()[0]) * 1024
    usage = os.statvfs(run_root)
    stat = Path("/proc/stat").read_text().splitlines()[0]
    dev = os.stat(run_root).st_dev
    disk_line = next((line for line in Path("/proc/diskstats").read_text().splitlines()
                      if line.split()[:2] == [str(os.major(dev)), str(os.minor(dev))]), None)
    pressure = {}
    for name in ("cpu", "memory", "io"):
        path = Path("/proc/pressure") / name
        if path.exists():
            pressure[name] = path.read_text().strip()
    return {"memory": info, "disk_available_bytes": usage.f_bavail * usage.f_frsize,
            "cpu_stat": stat, "diskstats": disk_line, "pressure": pressure}


def _docker(*args: str) -> str:
    return subprocess.run(("docker", *args), capture_output=True, text=True,
                          timeout=15, check=True).stdout.strip()


def _process_usage(pid: int) -> dict | None:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1].split()
        rss_pages = int(Path(f"/proc/{pid}/statm").read_text().split()[1])
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="replace").strip("\0").split("\0")
        return {"pid": pid, "rss_bytes": rss_pages * os.sysconf("SC_PAGE_SIZE"),
                "cpu_seconds": (int(stat[11]) + int(stat[12])) / os.sysconf("SC_CLK_TCK"),
                "cmdline": cmdline, "qemu_config": _qemu_config(cmdline)}
    except (FileNotFoundError, IndexError, ValueError, ProcessLookupError):
        return None


def sample(run_root: Path, interval_s: float, max_seconds: float) -> None:
    run_root = run_root.resolve()
    run_id = run_root.name
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", run_id) or not run_root.is_dir():
        raise ValueError("unsafe or missing run root")
    profile = {"run_id": run_id, "requested_guest_cpus": os.environ.get("OSCOMBO_GUEST_CPUS"),
               "requested_guest_ram": os.environ.get("OSCOMBO_GUEST_RAM"),
               "actual_qemu_config_source": "resource_samples.jsonl guests[].cmdline and qemu_config",
               "sample_interval_s": interval_s}
    (run_root / "resource_profile.json").write_text(json.dumps(profile, indent=2) + "\n")
    start, seen = time.monotonic(), False
    while time.monotonic() - start < max_seconds:
        ids = _docker("ps", "-q", "--filter", f"label=oscombo.run={run_id}").splitlines()
        seen = seen or bool(ids)
        guests = []
        for container_id in ids:
            full_id, pid_text = _docker("inspect", "--format", "{{.Id}} {{.State.Pid}}", container_id).split()
            sample = _process_usage(int(pid_text))
            if sample and sample["cmdline"] and Path(sample["cmdline"][0]).name.startswith("qemu-system-"):
                guests.append({"container_id": full_id, **sample})
        record = {"run_id": run_id, "time": time.time(), "guests": guests,
                  "rss_sum_bytes": sum(item["rss_bytes"] for item in guests),
                  "cpu_seconds_sum": sum(item["cpu_seconds"] for item in guests),
                  "host": _host_snapshot(run_root)}
        with (run_root / "resource_samples.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")
        if seen and not ids and any((run_root / f).exists() for f in ("result.json", "failure.json")):
            return
        time.sleep(interval_s)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root", type=Path)
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--max-seconds", type=float, default=5400)
    args = parser.parse_args()
    sample(args.run_root, args.interval, args.max_seconds)
