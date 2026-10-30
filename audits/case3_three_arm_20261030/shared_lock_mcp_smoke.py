"""One real Shared Guest, two independent desktop MCP processes, one input each.

This run is an infrastructure control. It does not execute or score Case 3.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
import time
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from oscombo.collab.data_to_deck import live_pilot as core
from oscombo.collab.data_to_deck.provenance import RunLedger


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def image_bytes(result) -> bytes:
    if result.isError:
        raise RuntimeError(f"MCP tool error: {result.content}")
    for item in result.content:
        if item.type == "image" and item.mimeType == "image/png":
            return base64.b64decode(item.data)
    raise RuntimeError("MCP tool did not return a PNG observation")


async def actor(role: str, url: str, lock_path: Path, run_root: Path,
                python: str, repo: Path, ready: asyncio.Event) -> None:
    actor_root = run_root / f"mcp_{role}"
    actor_root.mkdir()
    child_env = {name: os.environ[name] for name in
                 ("PATH", "HOME", "LANG", "LC_ALL", "VIRTUAL_ENV") if name in os.environ}
    child_env.update({
        "OSCOMBO_GUEST_URL": url,
        "OSCOMBO_ACTION_LOG": str(actor_root / "actions.jsonl"),
        "OSCOMBO_GUI_INPUT_LOCK_PATH": str(lock_path),
        "OSCOMBO_MAX_STEPS": "3",
        "PYTHONPATH": f"{repo}:{os.environ.get('OSWORLD_DIR', '')}",
    })
    server = StdioServerParameters(command=python,
        args=["-m", "oscombo.desktop_tools", "--mcp"], env=child_env, cwd=repo)
    async with stdio_client(server) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            first = await session.call_tool("screenshot", {})
            (run_root / "screenshots" / f"mcp_{role}_before.png").write_bytes(image_bytes(first))
            ready.set()
            await both_ready.wait()
            x = 140 if role == "A" else 180
            second = await session.call_tool("move", {"x": x, "y": 140})
            (run_root / "screenshots" / f"mcp_{role}_after.png").write_bytes(image_bytes(second))


async def drive_mcp(url: str, lock_path: Path, run_root: Path, python: str, repo: Path) -> None:
    global both_ready
    both_ready = asyncio.Event()
    ready_a, ready_b = asyncio.Event(), asyncio.Event()
    tasks = [asyncio.create_task(actor("A", url, lock_path, run_root, python, repo, ready_a)),
             asyncio.create_task(actor("B", url, lock_path, run_root, python, repo, ready_b))]
    try:
        await asyncio.wait_for(asyncio.gather(ready_a.wait(), ready_b.wait()), timeout=120)
        both_ready.set()
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=300)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def evaluate_logs(run_root: Path, lock_path: Path) -> dict:
    records = {}
    for role in "AB":
        log = run_root / f"mcp_{role}" / "actions.jsonl"
        rows = [json.loads(line) for line in log.read_text().splitlines()]
        if [row["tool"] for row in rows] != ["screenshot", "move"]:
            raise RuntimeError(f"{role} did not execute screenshot then input")
        action = rows[1]
        if not action.get("executed") or not action.get("input_lock", {}).get("enabled"):
            raise RuntimeError(f"{role} input was not executed under the lock")
        for phase in ("before", "after"):
            png = run_root / "screenshots" / f"mcp_{role}_{phase}.png"
            if png.stat().st_size < 1000:
                raise RuntimeError(f"{role} {phase} screenshot is empty")
        records[role] = action
    a, b = records["A"], records["B"]
    overlap = max(0.0, min(a["action_ended_at"], b["action_ended_at"]) -
                  max(a["action_started_at"], b["action_started_at"]))
    result = {"lock_path": str(lock_path), "input_overlap_s": overlap,
              "actors": {role: {"wait_s": records[role]["input_lock"]["wait_s"],
                                "held_s": records[role]["input_lock"]["held_s"],
                                "action_started_at": records[role]["action_started_at"],
                                "action_ended_at": records[role]["action_ended_at"]}
                         for role in "AB"}}
    if overlap > 0:
        raise RuntimeError(f"MCP inputs overlapped despite the action lock: {overlap}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--provider", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--mcp-python", required=True)
    args = parser.parse_args()
    run_root = args.run_root.resolve()
    run_root.mkdir(parents=True, exist_ok=False)
    (run_root / "screenshots").mkdir()
    run_id = run_root.name
    repo = Path(__file__).resolve().parents[2]
    core._write_ownership(run_root, {"run_id": run_id, "resources": [],
        "cleanup": "only exact owned oscombo.run label and full container ID"})
    ledger = RunLedger(run_root, {"run_id": run_id, "case_id": "CASE3-LOCK-SMOKE",
        "condition": "collaborative_shared", "guest_count": 1, "model_called": False,
        "started_at": time.time()})
    env = None
    current_id = None
    try:
        env, guest, current_id = core._boot_guest(run_root, run_id, "shared",
            args.image, args.provider.resolve(), args.runtime, ledger)
        marker = f"/tmp/{run_id}.marker"
        core._shell(guest, f"touch {marker} && test -e {marker}")
        lock_path = run_root / "gui_input.lock"
        asyncio.run(drive_mcp(guest.url, lock_path, run_root, args.mcp_python, repo))
        checks = evaluate_logs(run_root, lock_path)
        core._verify_container(current_id, run_id)
        os.environ["OSCOMBO_OVERLAY_DIR"] = str(run_root / "overlay" / "shared")
        os.environ["SWCUB_VM_OVERLAY"] = str(run_root / "overlay" / "shared")
        os.environ["OSCOMBO_RUN_LABEL"] = run_id
        env.is_environment_used = True
        env.reset()
        replacement, labels = core._owned_container(env, run_id)
        if replacement.id == current_id or not core._missing_container(current_id):
            raise RuntimeError("reset did not replace run-owned Guest")
        current_id = replacement.id
        core._shell(guest, f"test ! -e {marker}")
        checks["reset"] = {"new_container_id": current_id,
            "workspace_clean": True, "labels": labels}
        checks["status"] = "PASS"
        write_json(run_root / "result.json", checks)
        return 0
    except Exception as exc:
        write_json(run_root / "error.json", {"status": "INVALID_INFRA_OR_RUNNER_ERROR",
            "error_type": type(exc).__name__, "error": str(exc)})
        raise
    finally:
        if env is not None and current_id is not None:
            core._verify_container(current_id, run_id)
            env.close()
            if not core._missing_container(current_id):
                raise RuntimeError("run-owned Guest remains after close")
            core._append(run_root / "resource_actions.jsonl", {"event": "guest_closed",
                "full_container_id": current_id, "run_id": run_id})


if __name__ == "__main__":
    sys.exit(main())
