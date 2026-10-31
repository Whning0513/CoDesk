"""Run-labelled, read-only resource observations for Case 7 v2."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time


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
    while time.monotonic() - started < max_seconds:
        record = {"run_id": run_id, "time": time.time(), "guests": [],
                  "disk_available_bytes": os.statvfs(run_root).f_bavail * os.statvfs(run_root).f_frsize,
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
             and not any(r.get("sample_error") for r in rows))
    return {"valid": valid, "requested": requested, "actual_qemu_argv": cmds,
            "peak_observed_guests": peak, "samples": len(rows),
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
