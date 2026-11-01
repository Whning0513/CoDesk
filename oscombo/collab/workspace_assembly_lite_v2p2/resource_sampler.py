"""Run-labelled, read-only resource observations for Case 7 v2."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from . import filesystem_capacity


def _text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _children(pid: int) -> list[int]:
    result, queue = [], [pid]
    while queue:
        current = queue.pop()
        if current in result:
            continue
        result.append(current)
        for token in _text(f"/proc/{current}/task/{current}/children").split():
            if token.isdecimal():
                queue.append(int(token))
    return result


def _qemu(pid: int) -> dict | None:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        argv = [part.decode("utf-8", "replace") for part in raw if part]
        if not argv or "qemu-system-" not in Path(argv[0]).name:
            return None
        stat = _text(f"/proc/{pid}/stat").split(") ", 1)[1].split()
        status = _text(f"/proc/{pid}/status")
        io = _text(f"/proc/{pid}/io")
        fields = {}
        for line in (status + "\n" + io).splitlines():
            key, _, value = line.partition(":")
            if key in {"VmRSS", "VmSwap", "read_bytes", "write_bytes"}:
                fields[key] = value.strip()
        return {"pid": pid, "argv": argv,
                "cpu_seconds": (int(stat[11]) + int(stat[12])) / os.sysconf("SC_CLK_TCK"),
                "rss_bytes": int(fields["VmRSS"].split()[0]) * 1024,
                "process_created": int(stat[19]), "rss_and_io": fields}
    except (OSError, IndexError, KeyError, ValueError):
        return None


def sample(run_root: Path, interval: float, max_seconds: float) -> None:
    run_root = run_root.resolve()
    run_id = run_root.name
    output = run_root / "resource_samples_v2.jsonl"
    started = time.monotonic()
    seen = False
    try:
        preflight_path = Path(os.environ["CODESK_CASE7_FS_PREFLIGHT"])
        preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
        (run_root / "filesystem_preflight.json").write_text(
            json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (KeyError, OSError, ValueError):
        # Missing preflight is reported by summarize; do not stop Guest cleanup.
        pass
    try:
        filesystem_paths = filesystem_capacity.discover_paths(
            run_root, Path(os.environ.get("CODESK_CASE7_WORKTREE", str(run_root))))
        filesystem_error = None
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        filesystem_paths = None
        filesystem_error = f"filesystem discovery failed: {type(exc).__name__}"
    while time.monotonic() - started < max_seconds:
        record = {"run_id": run_id, "time": time.time(), "guests": [],
                  "disk_available_bytes": os.statvfs(run_root).f_bavail * os.statvfs(run_root).f_frsize,
                  "filesystem_capacity": (filesystem_capacity.snapshot(filesystem_paths)
                    if filesystem_paths is not None else
                    {"valid": False, "errors": [filesystem_error], "filesystems": {}}),
                  "host_meminfo": {line.split(":", 1)[0]: line.split(":", 1)[1].strip()
                    for line in _text("/proc/meminfo").splitlines()
                    if line.startswith(("MemAvailable:", "SwapTotal:", "SwapFree:"))},
                  "host_io_pressure": _text("/proc/pressure/io").strip()}
        try:
            ids = subprocess.run(["docker", "ps", "-q", "--filter", f"label=oscombo.run={run_id}"],
                                 check=True, capture_output=True, text=True, timeout=15).stdout.split()
            seen = seen or bool(ids)
            for cid in ids:
                output_text = subprocess.run(["docker", "inspect", "--format", "{{.Id}} {{.State.Pid}}", cid],
                    check=True, capture_output=True, text=True, timeout=15).stdout.split()
                full_id, root_pid = output_text[0], int(output_text[1])
                for pid in _children(root_pid):
                    guest = _qemu(pid)
                    if guest:
                        record["guests"].append({"container_id": full_id, **guest})
        except (OSError, subprocess.SubprocessError, IndexError, ValueError) as exc:
            record["sample_error"] = f"{type(exc).__name__}: {exc}"
        with output.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
        with (run_root / "qemu_process_resources.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"run_id": run_id, "time": record["time"],
                "guests": record["guests"], "guest_count": len(record["guests"])}, sort_keys=True) + "\n")
        if seen and not record["guests"] and (run_root / "result.json").exists():
            return
        if (run_root / "failure.json").exists():
            return
        time.sleep(interval)


def summarize(run_root: Path) -> dict:
    path = run_root / "resource_samples_v2.jsonl"
    if not path.is_file():
        return {"valid": False, "reason": "resource samples missing"}
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    provenance = json.loads((run_root / "provenance.json").read_text())
    result_path = run_root / "result.json"
    result = json.loads(result_path.read_text()) if result_path.exists() else {}
    cmds = {}
    for row in rows:
        for guest in row.get("guests", []):
            cmds[guest["container_id"]] = guest["argv"]
    def matching(argv):
        try:
            return argv[argv.index("-smp") + 1] == "8" and argv[argv.index("-m") + 1].upper() in {"8G", "8192", "8192M"}
        except (ValueError, IndexError):
            return False
    peak = max((len(r.get("guests", [])) for r in rows), default=0)
    requested = provenance.get("guest_resources_requested", {})
    expected_ids = {item.get("container_id") for item in provenance.get("guests", [])}
    sampled = [guest for row in rows for guest in row.get("guests", [])]
    required_fields = {"VmRSS", "VmSwap", "read_bytes", "write_bytes"}
    times = sorted(float(row["time"]) for row in rows if isinstance(row.get("time"), (int, float)))
    max_gap = max((b - a for a, b in zip(times, times[1:])), default=float("inf"))
    started, elapsed = provenance.get("started_at"), result.get("elapsed_s")
    timing_covered = (isinstance(started, (int, float)) and isinstance(elapsed, (int, float)) and
                      len(times) >= 2 and times[0] <= started + 60 and
                      times[-1] >= started + elapsed - 60 and max_gap <= 60)
    filesystems = [row.get("filesystem_capacity", {}) for row in rows]
    filesystem_errors, minima = [], {}
    if not filesystems:
        filesystem_errors.append("filesystem samples missing")
    for index, item in enumerate(filesystems):
        if not isinstance(item, dict) or item.get("valid") is not True:
            filesystem_errors.append(f"filesystem sample {index} missing or below a limit")
        elif not isinstance(item.get("filesystems"), dict) or set(item["filesystems"]) != set(filesystem_capacity.LABELS):
            filesystem_errors.append(f"filesystem sample {index} has incomplete labels")
    for label in filesystem_capacity.LABELS:
        values = [item.get("filesystems", {}).get(label, {})
                  for item in filesystems if isinstance(item, dict) and isinstance(item.get("filesystems"), dict)]
        if len(values) != len(filesystems) or not values or any(
                not isinstance(value, dict) or not isinstance(value.get("available_bytes"), int)
                or not isinstance(value.get("available_inodes"), int)
                or not isinstance(value.get("device"), int) or not isinstance(value.get("path"), str)
                or not Path(value["path"]).is_absolute() for value in values):
            filesystem_errors.append(f"{label} capacity evidence incomplete")
            continue
        minima[label] = {"available_bytes": min(v["available_bytes"] for v in values),
                         "available_inodes": min(v["available_inodes"] for v in values)}
        if minima[label]["available_bytes"] < filesystem_capacity.MIN_FREE_BYTES:
            filesystem_errors.append(f"{label} below 15 GiB during run")
        if minima[label]["available_inodes"] < filesystem_capacity.MIN_FREE_INODES:
            filesystem_errors.append(f"{label} below {filesystem_capacity.MIN_FREE_INODES} inodes during run")
        if len({(v["path"], v["device"]) for v in values}) != 1:
            filesystem_errors.append(f"{label} path or device changed during run")
    try:
        preflight = json.loads((run_root / "filesystem_preflight.json").read_text())
        if preflight.get("valid") is not True or set(preflight.get("filesystems", {})) != set(filesystem_capacity.LABELS):
            raise ValueError("preflight invalid or incomplete")
        for label in filesystem_capacity.LABELS:
            before = preflight["filesystems"][label]
            values = [item["filesystems"][label] for item in filesystems]
            if (before["available_bytes"] < filesystem_capacity.MIN_FREE_BYTES
                    or before["available_inodes"] < filesystem_capacity.MIN_FREE_INODES
                    or any(value["device"] != before["device"] for value in values)
                    or (label != "run" and any(value["path"] != before["path"] for value in values))):
                filesystem_errors.append(f"{label} differs from passing preflight")
    except (OSError, ValueError, TypeError, KeyError):
        filesystem_errors.append("passing filesystem preflight evidence missing or invalid")
    filesystem_valid = not filesystem_errors
    valid = (requested == {"cpus": "8", "ram": "8G"} and bool(cmds)
             and len(expected_ids) == int(provenance.get("guest_count", 0)) > 0
             and None not in expected_ids and expected_ids <= set(cmds)
             and peak >= int(provenance.get("guest_count", 0))
             and all(matching(argv) for argv in cmds.values())
             and all(any(guest["container_id"] == cid and
                         required_fields <= set(guest.get("rss_and_io", {})) for guest in sampled)
                     for cid in expected_ids)
             and all({"MemAvailable", "SwapTotal", "SwapFree"} <= set(row.get("host_meminfo", {}))
                     and bool(row.get("host_io_pressure")) for row in rows)
             and timing_covered and filesystem_valid and not any(r.get("sample_error") for r in rows))
    return {"valid": valid, "requested": requested, "actual_qemu_argv": cmds,
            "peak_observed_guests": peak, "samples": len(rows), "timing_covered": timing_covered,
            "filesystem_capacity_valid": filesystem_valid, "filesystem_minima": minima,
            "filesystem_capacity_errors": filesystem_errors,
            "max_sample_gap_s": round(max_gap, 3) if times and len(times) >= 2 else None,
            "sample_errors": [r["sample_error"] for r in rows if r.get("sample_error")]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root", type=Path)
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--max-seconds", type=float, default=7200)
    parser.add_argument("--summarize", action="store_true")
    args = parser.parse_args()
    if args.summarize:
        if not ((args.run_root / "result.json").exists() or (args.run_root / "failure.json").exists()):
            raise RuntimeError("do not finalize resource provenance while the run is active")
        result = summarize(args.run_root)
        (args.run_root / "resource_audit.json").write_text(json.dumps(result, indent=2) + "\n")
        provenance_path = args.run_root / "provenance.json"
        provenance = json.loads(provenance_path.read_text())
        provenance["guest_resources_observed"] = result
        temporary = provenance_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
        temporary.replace(provenance_path)
        print(json.dumps(result))
    else:
        sample(args.run_root, args.interval, args.max_seconds)
