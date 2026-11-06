"""Model runner for Spreadsheet Handoff Lite v1.3.

Importing this module is offline. Only ``run_model_episode`` starts Guests and
the allowlisted Responses relay. The three arms share one contract and differ
only in desktop topology and the optional existing per-action GUI lock.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shlex
import subprocess
import sys
import threading
import time
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from oscombo.collab import lite_file_guest_pilot as shared_pilot
from oscombo.collab.data_to_deck import live_pilot as core
from oscombo.collab.data_to_deck.collab_tools import CollaborationClient
from oscombo.collab.data_to_deck.protocol import ProtocolStore, make_server
from oscombo.collab.data_to_deck.provenance import RunLedger, collect_artifacts
from oscombo.collab.data_to_deck.workspace_bridge import SavedArtifactBridge
from oscombo.collab.spreadsheet_handoff_lite_v1_2 import relay_transport
from oscombo.responses_tool_image_relay import make_server as make_allowlisted_relay

from . import adapter, fixtures, oracle, resource_gate_amendment, spec


ARM_CONDITIONS = {
    "isolated": ("collaborative_isolated", False),
    "shared": ("collaborative_shared", False),
    "sharedlock": ("collaborative_shared", True),
}
MODEL_TIMEOUT_S = 1200
MODEL_EFFORT = "medium"
REQUEST_RETRIES = 2
MODEL_RUNNER_VERSION = "1.3.2"
PILOT_STEP_MIN = 4
PILOT_STEP_MAX = 12
ACTOR_TOOL_ALLOWLIST = frozenset({
    "screenshot", "click", "drag", "move", "type_text", "key", "scroll", "wait",
    "declare_infeasible", "send_message", "read_messages", "send_attachment",
    "read_attachment", "publish_saved_artifact", "list_saved_artifacts",
})


def _role_budget(pilot_step_limit: int | None = None) -> dict[str, dict[str, int | None]]:
    """Return the frozen formal budget or an explicit small diagnostic cap."""
    if pilot_step_limit is None:
        return {role: dict(budget) for role, budget in spec.ROLE_BUDGET.items()}
    if (isinstance(pilot_step_limit, bool) or not isinstance(pilot_step_limit, int)
            or not PILOT_STEP_MIN <= pilot_step_limit <= PILOT_STEP_MAX):
        raise ValueError(
            f"pilot step limit must be between {PILOT_STEP_MIN} and {PILOT_STEP_MAX} per role")
    return {
        role: {**budget, "steps": min(int(budget["steps"]), pilot_step_limit)}
        for role, budget in spec.ROLE_BUDGET.items()
    }


def model_contract(arm: str, *, model: str, base_url: str, api_key_env: str,
                   mcp_python: str, pilot_step_limit: int | None = None) -> dict[str, Any]:
    """Return the frozen, secret-free actor/runtime contract for one arm."""
    if arm not in ARM_CONDITIONS:
        raise ValueError(f"unknown v1.3 model arm: {arm!r}")
    if pilot_step_limit is not None and arm != "isolated":
        raise ValueError("the diagnostic pilot is Isolated-only; formal arms share the full budget")
    condition, lock_enabled = ARM_CONDITIONS[arm]
    if not model or not base_url or not api_key_env or not mcp_python:
        raise ValueError("model, base_url, api_key_env and mcp_python are required")
    return {
        "case_id": spec.CASE_ID,
        "case_version": spec.CASE_VERSION,
        "model_runner_version": MODEL_RUNNER_VERSION,
        "execution_mode": "diagnostic_pilot" if pilot_step_limit is not None else "formal",
        "pilot_step_limit": pilot_step_limit,
        "arm": arm,
        "condition": condition,
        "guest_count": 2 if arm == "isolated" else 1,
        "model": model,
        "base_url": base_url,
        "api_key_env": api_key_env,
        "mcp_python": mcp_python,
        "effort": MODEL_EFFORT,
        "model_timeout_s": MODEL_TIMEOUT_S,
        "request_retries": REQUEST_RETRIES,
        "role_budget": _role_budget(pilot_step_limit),
        "yield_wait_lifecycle": True,
        "actor_mcp_only": True,
        "gui_input_lock": lock_enabled,
        "actor_prompts_sha256": {
            role: hashlib.sha256(getattr(spec, f"AGENT_{role}_INSTRUCTION").encode()).hexdigest()
            for role in "AB"
        },
        "fixture_names": dict(spec.FIXTURE_NAMES),
        "outputs": dict(spec.OUTPUTS),
    }


def _tool_leaf(name: str) -> str:
    return re.split(r"(?:\.|__)", name)[-1]


def _message_discloses_business_quantity(body: str) -> bool:
    """Detect task numbers while permitting normal revision IDs, dates and versions."""
    scrubbed = re.sub(
        r"\b(?:saved\s+)?(?:rev(?:ision)?|version)\s*(?:number|no\.?|#|:|=)?\s*"
        r"(?:r\s*)?\d+(?:[._-]\d+)*\b", " ", body, flags=re.I)
    scrubbed = re.sub(r"\br\d{6,}\b", " ", scrubbed, flags=re.I)
    scrubbed = re.sub(r"\bv\d+(?:\.\d+){1,3}\b", " ", scrubbed, flags=re.I)
    scrubbed = re.sub(r"\b\d{4}-\d{1,2}-\d{1,2}(?:[T ]\d{1,2}:\d{2}(?::\d{2})?Z?)?\b", " ", scrubbed)
    # The role contract asks A for a readiness-only message, so remaining
    # numeric tokens indicate business or calculation content.
    if re.search(r"(?<![A-Za-z])\d+(?:[,.]\d+)?", scrubbed):
        return True
    number_words = ("zero|one|two|three|four|five|six|seven|eight|nine|ten|"
                    "eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|"
                    "eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|"
                    "eighty|ninety|hundred|thousand")
    units = r"(?:units?|cartons?|cases?|items?|pieces?|dollars?|usd)"
    quantity = rf"(?:{number_words})(?:[- ](?:{number_words}))*"
    return bool(re.search(rf"\b{quantity}\s+{units}\b", scrubbed, re.I)
                or re.search(rf"\b{units}\b[^.!?]{{0,30}}\b{quantity}\b", scrubbed, re.I))


def audit_actor_tool_boundary(run_root: Path) -> dict[str, Any]:
    """Fail closed unless both Actor Codex logs show only contracted tools."""
    actors: dict[str, Any] = {}
    malformed = 0
    missing_session = []
    for role in "AB":
        session_root = run_root / "actor_runs" / role / role / "codex_home" / "sessions"
        calls: Counter[str] = Counter()
        argument_rows: list[dict[str, Any]] = []
        paths = sorted(session_root.rglob("*.jsonl")) if session_root.is_dir() else []
        if not paths:
            missing_session.append(role)
        for path in paths:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    row = json.loads(line)
                except ValueError:
                    malformed += 1
                    continue
                if not isinstance(row, dict) or row.get("type") != "response_item":
                    continue
                item = row.get("payload") or {}
                if not isinstance(item, dict) or item.get("type") not in {"function_call", "custom_tool_call"}:
                    continue
                name = str(item.get("name") or "<unnamed>")
                calls[name] += 1
                args = item.get("arguments", "")
                if isinstance(args, dict):
                    args_text = json.dumps(args, ensure_ascii=False, sort_keys=True)
                else:
                    args_text = str(args)
                # Keep only the minimum non-secret metadata needed for handoff review.
                peer_paths = re.findall(r"/tmp/sh13/incoming/A/[^\s\"']+", args_text)
                argument_rows.append({"name": name, "leaf": _tool_leaf(name),
                                      "order": sum(calls.values()),
                                      "peer_revision_paths": peer_paths,
                                      "enter_key": (_tool_leaf(name) == "key" and
                                          bool(re.search(r"\b(?:enter|return)\b", args_text, re.I))),
                                      "argument_bytes": len(args_text)})
        total = sum(calls.values())
        outside = {name: count for name, count in sorted(calls.items())
                   if _tool_leaf(name) not in ACTOR_TOOL_ALLOWLIST}
        actors[role] = {"session_files": len(paths), "total_tool_calls": total,
                        "outside_gui_collaboration_contract": outside,
                        "call_evidence": argument_rows}
    errors = []
    if missing_session:
        errors.append("missing_codex_session_for_actor:" + ",".join(missing_session))
    if malformed:
        errors.append(f"malformed_session_records:{malformed}")
    for role in "AB":
        if actors[role]["total_tool_calls"] == 0:
            errors.append(f"no_actor_tool_calls:{role}")
        if actors[role]["outside_gui_collaboration_contract"]:
            errors.append(f"actor_used_tools_outside_contract:{role}")
    return {"valid": not errors, "errors": errors, "actors": actors,
            "allowed_tool_names": sorted(ACTOR_TOOL_ALLOWLIST),
            "scope": "Codex rollout function/custom-tool calls only; no prompts or tool arguments emitted"}


def audit_model_handoff(run_root: Path, bridge_snapshot: dict[str, Any],
                        protocol_events: list[dict[str, Any]]) -> dict[str, Any]:
    """Check handoff chronology without treating a revision/hash alone as proof."""
    boundary = audit_actor_tool_boundary(run_root)
    a_rev = bridge_snapshot.get("A", {}) if isinstance(bridge_snapshot, dict) else {}
    b_rev = bridge_snapshot.get("B", {}) if isinstance(bridge_snapshot, dict) else {}
    messages = [event for event in protocol_events if event.get("type") == "message"
                and event.get("actor") == "A" and event.get("recipient") in {"B", "all"}]
    bridge_rows = []
    bridge_events = run_root / "workspace_versions" / "events.jsonl"
    if bridge_events.is_file():
        for line in bridge_events.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                bridge_rows.append(row)
    committed_a = [row for row in bridge_rows if row.get("event") == "revision_committed"
                   and row.get("actor") == "A"]
    peer_verified = [row for row in bridge_rows if row.get("event") == "peer_view_verified"
                     and row.get("actor") == "A" and row.get("peer") == "B"]
    ready_message = next((msg for msg in messages
                          if committed_a and float(msg.get("timestamp", 0)) >=
                          float(committed_a[-1].get("time", float("inf")))), None)
    b_calls = boundary.get("actors", {}).get("B", {}).get("call_evidence", [])
    b_stdout = run_root / "actor_runs" / "B" / "B" / "stdout.log"
    b_observed_message_ids = core._observed_peer_message_ids(b_stdout)
    list_index = next((row["order"] for row in b_calls if _tool_leaf(row["name"]) == "list_saved_artifacts"), None)
    message_index = next((row["order"] for row in b_calls if _tool_leaf(row["name"]) == "read_messages"), None)
    expected_peer_path = (spec.TASK_ROOT + "/" + str(a_rev.get("peer_view_path", "")))
    exact_path_call = next((row for row in b_calls
                            if expected_peer_path in row.get("peer_revision_paths", [])), None)
    peer_path_index = exact_path_call.get("order") if exact_path_call else None
    enter_index = next((row["order"] for row in b_calls if row.get("enter_key")
                        and row["order"] > (peer_path_index or float("inf"))), None)
    screenshot_index = next((row["order"] for row in b_calls
                             if row.get("leaf") == "screenshot" and
                             peer_path_index is not None and row["order"] > peer_path_index), None)
    publish_index = next((row["order"] for row in reversed(b_calls)
                          if row.get("leaf") == "publish_saved_artifact"), None)
    a_message_body = str(ready_message.get("body", "")) if ready_message else ""
    explicit_number = _message_discloses_business_quantity(a_message_body)
    checks = {
        "A_revision_committed": bool(committed_a and int(a_rev.get("revision", 0)) > 0),
        "A_peer_view_verified_readonly": bool(peer_verified and a_rev.get("delivered") is True
                                               and a_rev.get("peer_view_path")),
        "A_ready_message_after_revision": bool(ready_message),
        "A_message_has_no_numeric_answer": bool(ready_message and not explicit_number),
        "B_read_artifact_metadata_before_peer_open": bool(list_index and peer_path_index and list_index < peer_path_index),
        "B_read_message_before_peer_open": bool(message_index and peer_path_index and message_index < peer_path_index),
        "B_received_A_ready_message_in_tool_result": bool(ready_message and
                                                            ready_message.get("message_id") in b_observed_message_ids),
        "B_typed_exact_peer_revision_path": bool(peer_path_index),
        "B_pressed_key_after_peer_path": bool(enter_index),
        "B_screenshot_after_peer_open": bool(screenshot_index),
        "B_published_order_after_peer_read": bool(b_rev and int(b_rev.get("revision", 0)) > 0
                                                  and publish_index and peer_path_index
                                                  and publish_index > peer_path_index),
    }
    return {"valid": all(checks.values()), "checks": checks,
            "a_revision": a_rev.get("revision"), "a_peer_view_path": a_rev.get("peer_view_path"),
            "b_revision": b_rev.get("revision"), "ready_message_id": (ready_message or {}).get("message_id"),
            "expected_peer_gui_path": expected_peer_path,
            "actor_tool_order": {"B_list_artifacts": list_index, "B_read_messages": message_index,
                                 "B_peer_path": peer_path_index, "B_screenshot": screenshot_index,
                                 "B_enter": enter_index, "B_publish": publish_index},
            "B_observed_message_ids": sorted(b_observed_message_ids),
            "visual_review_required": True,
            "visual_review_note": "The transcript proves tool chronology and requested file path, not that the correct cell was visually read."}


def map_model_result(*, oracle_result: dict[str, Any], actor_results: dict[str, dict[str, Any]],
                     handoff: dict[str, Any], bridge_ok: bool,
                     relay_audit: dict[str, Any], actor_tool_audit: dict[str, Any],
                     postscore_lifecycle_ok: bool, reset_ok: bool) -> str:
    """Separate infra/transport faults from ordinary coordination or GUI failure."""
    infrastructure_valid = (bridge_ok and relay_audit.get("valid") is True
                            and actor_tool_audit.get("valid") is True
                            and postscore_lifecycle_ok and reset_ok)
    if not infrastructure_valid:
        return "INVALID_INFRA_OR_RUNNER_ERROR"
    if any(result.get("status") == "error" or
           (result.get("status") == "timeout" and int(result.get("steps", 0)) == 0)
           for result in actor_results.values()):
        return "INVALID_INFRA_OR_RUNNER_ERROR"
    return "PASS" if bool(oracle_result.get("joint_success")) and handoff.get("valid") is True else "FAIL"


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def _instrument_guest_screenshots(guest: Any, run_root: Path,
                                  log_lock: threading.Lock | None = None) -> None:
    """Record screenshot latency at the v1.3 adapter boundary, without Harness changes."""
    original = guest.screenshot
    log_path = run_root / "screenshot_timing.jsonl"
    log_lock = log_lock or threading.Lock()
    def timed_screenshot(*args, **kwargs):
        started_at = time.time()
        try:
            return original(*args, **kwargs)
        finally:
            ended_at = time.time()
            row = {"actor": guest.actor, "guest_key": guest.guest_key,
                   "started_at": started_at, "ended_at": ended_at,
                   "elapsed_s": round(ended_at - started_at, 4)}
            with log_lock, log_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, sort_keys=True) + "\n")
    guest.screenshot = timed_screenshot


def summarize_execution_metrics(run_root: Path,
                                actor_results: dict[str, dict[str, Any]],
                                run_started_at: float | None = None) -> dict[str, Any]:
    relay = _read_jsonl(run_root / "codex_relay_events.jsonl")
    gui = _read_jsonl(run_root / "gui_actions.jsonl")
    screenshots = _read_jsonl(run_root / "screenshot_timing.jsonl")
    calls = {role: {"requests": 0, "latency_s": 0.0} for role in "AB"}
    gui_time = {role: 0.0 for role in "AB"}
    shot = {role: {"count": 0, "latency_s": 0.0} for role in "AB"}
    for row in relay:
        role = row.get("actor")
        if role in calls:
            calls[role]["requests"] += 1
            calls[role]["latency_s"] += float(row.get("elapsed_s") or 0.0)
    for row in gui:
        role = row.get("actor")
        if role in gui_time:
            gui_time[role] += float(row.get("duration_s") or 0.0)
    for row in screenshots:
        role = row.get("actor")
        if role in shot:
            shot[role]["count"] += 1
            shot[role]["latency_s"] += float(row.get("elapsed_s") or 0.0)
    actor_wall_elapsed = {}
    actor_started_at = []
    for role in "AB":
        calls[role]["latency_s"] = round(calls[role]["latency_s"], 3)
        gui_time[role] = round(gui_time[role], 3)
        shot[role]["latency_s"] = round(shot[role]["latency_s"], 3)
        wall = actor_results.get(role, {})
        if wall.get("started_at") is not None and wall.get("ended_at") is not None:
            actor_started_at.append(float(wall["started_at"]))
            actor_wall_elapsed[role] = round(float(wall["ended_at"]) - float(wall["started_at"]), 3)
    return {"model_requests": calls, "gui_action_elapsed_s": gui_time,
            "screenshot_calls": shot,
            "actor_wall_elapsed_s": actor_wall_elapsed,
            "setup_elapsed_s": (round(min(actor_started_at) - run_started_at, 3)
                                if run_started_at is not None and actor_started_at else None),
            "actor_wall_elapsed_includes_wait": True,
            "screenshot_latency_scope": "LoggedGuest.screenshot calls; actor role label from run context"}


def docker_data_root_matches(expected_root: str, actual_root: str) -> bool:
    """Require the selected Docker daemon's data-root to match a /data2 path."""
    expected = Path(expected_root).resolve(strict=False)
    actual = Path(actual_root).resolve(strict=False)
    data2 = Path("/data2").resolve(strict=False)
    try:
        expected.relative_to(data2)
        actual.relative_to(data2)
    except ValueError:
        return False
    return actual == expected


def docker_image_id_matches(expected_id: str, actual_id: str) -> bool:
    """Require a pinned Docker image content ID, not an unverified mutable tag."""
    return (bool(re.fullmatch(r"sha256:[0-9a-f]{64}", expected_id or ""))
            and expected_id == actual_id)


def verify_run_owned_cache(env: Any, run_root: Path, guest_key: str,
                           stage: str) -> dict[str, Any]:
    """Verify cache ownership, allowing task cache creation only during boot."""
    if guest_key not in {"shared", "A", "B"}:
        raise ValueError("unknown Case 6 Guest key for cache ownership")
    if stage not in {"boot", "reset"}:
        raise ValueError("cache validation stage must be 'boot' or 'reset'")
    root = run_root.resolve(strict=True)
    owned_root = root / "cache" / guest_key
    resolved_owned_root = owned_root.resolve(strict=False)
    try:
        resolved_owned_root.relative_to(root / "cache")
    except ValueError as exc:
        raise ValueError("Guest cache root escapes the run-owned cache directory") from exc

    setup = getattr(env, "setup_controller", None)
    observed = {
        "DesktopEnv.cache_dir_base": getattr(env, "cache_dir_base", None),
        "SetupController.cache_dir": getattr(setup, "cache_dir", None),
    }
    resolved = {}
    for label, path in observed.items():
        if not isinstance(path, (str, os.PathLike)) or not str(path):
            raise ValueError(f"{label} is unavailable; cannot verify Guest cache ownership")
        resolved[label] = Path(path).resolve(strict=False)
        try:
            resolved[label].relative_to(resolved_owned_root)
        except ValueError as exc:
            raise ValueError(f"{label} is outside this Guest's run-owned cache directory") from exc
        if label == "DesktopEnv.cache_dir_base" and resolved[label] != resolved_owned_root:
            raise ValueError(f"{label} is outside this Guest's run-owned cache directory")

    task_cache = getattr(env, "cache_dir", None)
    task_cache_path = None
    task_cache_present = (isinstance(task_cache, (str, os.PathLike))
                          and bool(os.fspath(task_cache)))
    if task_cache is not None and not task_cache_present:
        raise ValueError("DesktopEnv task cache path is malformed")
    if stage == "reset" and not task_cache_present:
        raise ValueError("DesktopEnv task cache path is missing after reset")
    if task_cache_present:
        task_cache_path = Path(task_cache).resolve(strict=False)
        try:
            task_cache_path.relative_to(resolved_owned_root)
        except ValueError as exc:
            raise ValueError("DesktopEnv task cache escapes this Guest's run-owned cache directory") from exc
    return {"guest_key": guest_key, "validation_stage": stage,
            "cache_root": str(resolved_owned_root),
            "desktop_env_cache_dir_base": str(resolved["DesktopEnv.cache_dir_base"]),
            "setup_controller_cache_dir": str(resolved["SetupController.cache_dir"]),
            "desktop_env_task_cache_dir": str(task_cache_path) if task_cache_path else None,
            "verified": True}


def verify_run_owned_guest_resources(container: Any, env: Any, image: str,
                                     run_root: Path, guest_key: str,
                                     stage: str) -> dict[str, Any]:
    """Verify the current Guest's base mount, overlay, cache, and pinned runtime."""
    attrs = getattr(container, "attrs", None)
    if not isinstance(attrs, dict):
        raise ValueError("Guest container inspection attributes are unavailable")
    mounts = attrs.get("Mounts")
    if not isinstance(mounts, list):
        raise ValueError("Guest mount inspection evidence is unavailable")
    base_mount = next((row for row in mounts if isinstance(row, dict)
                       and row.get("Destination") == "/System.qcow2"), None)
    provider = getattr(env, "provider", None)
    overlay = getattr(provider, "_oscombo_overlay", None)
    if not isinstance(overlay, (str, os.PathLike)) or not str(overlay):
        raise ValueError("Guest QEMU overlay path is unavailable")
    cache = verify_run_owned_cache(env, run_root, guest_key, stage)
    resource_gate_amendment.verify_guest_mount_and_writes(
        image_path=image, run_root=run_root, mount=base_mount,
        overlay_path=overlay, cache_path=cache["cache_root"])
    expected_runtime = os.environ.get("CODESK_CASE6_V13_RUNTIME_IMAGE_ID")
    actual_runtime = attrs.get("Image")
    if expected_runtime and not docker_image_id_matches(expected_runtime, actual_runtime):
        raise ValueError("Guest container runtime image ID differs from the frozen pin")
    return {"guest_key": guest_key, "validation_stage": stage,
            "container_id": getattr(container, "id", None),
            "runtime_image_id": actual_runtime, "base_mount": base_mount,
            "overlay_path": str(Path(overlay).resolve(strict=True)),
            "cache": cache, "verified": True}


def filesystem_capacity_ok(available_kib: int, available_inodes: int,
                           min_gib: int = 15, min_inodes: int = 1024) -> bool:
    """Pure capacity gate for shell preflight and its offline tests."""
    return (type(available_kib) is int and type(available_inodes) is int
            and available_kib >= min_gib * 1024 * 1024
            and available_inodes >= min_inodes)


def osworld_source_identity(provider: Path) -> dict[str, str]:
    """Pin local OSWorld HEAD plus tracked worktree/index diff; reject untracked files."""
    try:
        head_result = subprocess.run(
            ["git", "-C", str(provider), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, timeout=10)
        diff_result = subprocess.run(
            ["git", "-C", str(provider), "diff", "--binary", "HEAD"],
            check=True, capture_output=True, timeout=30)
        untracked_result = subprocess.run(
            ["git", "-C", str(provider), "ls-files", "--others", "--exclude-standard"],
            check=True, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("cannot read the local OSWorld source identity") from exc
    if untracked_result.stdout.strip():
        raise RuntimeError("OSWorld checkout has untracked non-ignored files")
    commit = head_result.stdout.strip()
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", commit):
        raise RuntimeError("local OSWorld HEAD is not a full Git commit ID")
    return {"commit": commit,
            "diff_sha256": hashlib.sha256(diff_result.stdout).hexdigest()}


def osworld_source_matches(expected_commit: str, expected_diff_sha256: str,
                           actual: dict[str, str]) -> bool:
    """Require a full HEAD pin and exact binary diff hash for the RO-base cohort."""
    return (bool(re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", expected_commit or ""))
            and bool(re.fullmatch(r"[0-9a-f]{64}", expected_diff_sha256 or ""))
            and actual.get("commit") == expected_commit
            and actual.get("diff_sha256") == expected_diff_sha256)


def _write_no_bytecode_python(run_root: Path, python: str) -> str:
    """Create a v1.3-local MCP interpreter wrapper that cannot write .pyc files."""
    tool_dir = run_root / "tools"
    tool_dir.mkdir(parents=True, exist_ok=True)
    wrapper = tool_dir / "python-no-bytecode"
    wrapper.write_text("#!/usr/bin/env bash\nset -e\nexport PYTHONDONTWRITEBYTECODE=1\nexec " +
                       shlex.quote(str(python)) + " \"$@\"\n", encoding="utf-8")
    wrapper.chmod(0o700)
    return str(wrapper)


def _start_allowlisted_relay(run_root: Path, upstream: str, api_key_env: str,
                             client_token: str):
    """Use the existing relay implementation in-process; never log provider credentials."""
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise RuntimeError(f"provider credential environment variable is missing: {api_key_env}")
    server = make_allowlisted_relay("127.0.0.1", 0, upstream, api_key,
        run_root / "codex_relay_events.jsonl", actor_mcp_only=True,
        client_token=client_token)
    thread = threading.Thread(target=server.serve_forever, daemon=True,
                              name=f"case6-v13-relay-{run_root.name}")
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_port}/v1"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _wall_interval_overlap(actor_results: dict[str, dict[str, Any]]) -> float:
    try:
        a, b = actor_results["A"], actor_results["B"]
        return round(max(0.0, min(float(a["ended_at"]), float(b["ended_at"])) -
                         max(float(a["started_at"]), float(b["started_at"]))), 3)
    except (KeyError, TypeError, ValueError):
        return 0.0


def _merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[list[float]] = []
    for start, end in sorted((a, b) for a, b in intervals if b > a):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(a, b) for a, b in merged]


def _subtract_intervals(intervals: list[tuple[float, float]],
                        excluded: list[tuple[float, float]]) -> list[tuple[float, float]]:
    remaining = _merge_intervals(intervals)
    for cut_start, cut_end in _merge_intervals(excluded):
        next_rows = []
        for start, end in remaining:
            if cut_end <= start or cut_start >= end:
                next_rows.append((start, end))
            else:
                if start < cut_start:
                    next_rows.append((start, cut_start))
                if cut_end < end:
                    next_rows.append((cut_end, end))
        remaining = next_rows
    return remaining


def _intersection_duration(left: list[tuple[float, float]],
                           right: list[tuple[float, float]]) -> float:
    a_rows, b_rows = _merge_intervals(left), _merge_intervals(right)
    i = j = 0
    total = 0.0
    while i < len(a_rows) and j < len(b_rows):
        start = max(a_rows[i][0], b_rows[j][0])
        end = min(a_rows[i][1], b_rows[j][1])
        total += max(0.0, end - start)
        if a_rows[i][1] <= b_rows[j][1]:
            i += 1
        else:
            j += 1
    return round(total, 3)


def compute_overlap_summary(relay_events: list[dict[str, Any]],
                            gui_actions: list[dict[str, Any]],
                            lifecycle_events: list[dict[str, Any]],
                            actor_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Recompute activity overlap from timestamped model requests and GUI actions.

    The active measure is a conservative observable lower bound: union of
    provider request intervals and actual LoggedGuest GUI action intervals,
    minus recorded handoff suspensions. It does not count unobserved local
    model deliberation as active time.
    """
    active: dict[str, list[tuple[float, float]]] = {role: [] for role in "AB"}
    gui: dict[str, list[tuple[float, float]]] = {role: [] for role in "AB"}
    suspended: dict[str, list[tuple[float, float]]] = {role: [] for role in "AB"}
    for row in relay_events:
        role = row.get("actor")
        try:
            start, end = float(row["started_at"]), float(row["time"])
        except (KeyError, TypeError, ValueError):
            continue
        if role in active and end > start:
            active[role].append((start, end))
    for row in gui_actions:
        role = row.get("actor")
        try:
            start, end = float(row["started_at"]), float(row["ended_at"])
        except (KeyError, TypeError, ValueError):
            continue
        if role in active and end > start:
            active[role].append((start, end))
            gui[role].append((start, end))
    open_wait: dict[str, float] = {}
    for row in sorted(lifecycle_events, key=lambda x: float(x.get("time", 0))):
        role, event = row.get("actor"), row.get("event")
        if role not in suspended:
            continue
        try:
            stamp = float(row["time"])
        except (KeyError, TypeError, ValueError):
            continue
        if event == "suspended_for_peer_handoff":
            open_wait[role] = stamp
        elif event in {"woken_by_peer_handoff", "peer_handoff_wait_expired",
                       "peer_finished_without_handoff"} and role in open_wait:
            if stamp > open_wait[role]:
                suspended[role].append((open_wait[role], stamp))
            del open_wait[role]
    for role, start in open_wait.items():
        intervals = active[role]
        end = max((right for _, right in intervals), default=start)
        if end > start:
            suspended[role].append((start, end))
    active = {role: _subtract_intervals(intervals, suspended[role])
              for role, intervals in active.items()}
    try:
        actor_wall = {role: (float(actor_results[role]["started_at"]),
                             float(actor_results[role]["ended_at"])) for role in "AB"}
        wall_overlap = max(0.0, min(actor_wall["A"][1], actor_wall["B"][1]) -
                           max(actor_wall["A"][0], actor_wall["B"][0]))
    except (KeyError, TypeError, ValueError):
        wall_overlap = 0.0
    return {
        "wall_clock_interval_overlap_s": round(wall_overlap, 3),
        "observed_active_request_or_gui_overlap_s": _intersection_duration(active["A"], active["B"]),
        "observed_shared_gui_action_overlap_s": _intersection_duration(gui["A"], gui["B"]),
        "suspended_wait_s": {role: round(sum(b - a for a, b in _merge_intervals(rows)), 3)
                             for role, rows in suspended.items()},
        "activity_sources": ["codex_relay_events.started_at/time", "gui_actions.started_at/ended_at",
                             "actor_lifecycle.jsonl suspend/wake intervals"],
        "active_overlap_scope": "observable lower bound; excludes unobserved local model deliberation",
    }


def _usage_by_actor(run_root: Path) -> dict[str, dict[str, int]]:
    result = {role: {"input_tokens": 0, "output_tokens": 0, "requests": 0} for role in "AB"}
    for row in _read_jsonl(run_root / "codex_relay_events.jsonl"):
        role = row.get("actor")
        if role not in result:
            continue
        usage = row.get("usage") or {}
        result[role]["input_tokens"] += int(usage.get("input_tokens") or 0)
        result[role]["output_tokens"] += int(usage.get("output_tokens") or 0)
        result[role]["requests"] += 1
    return result


def run_model_episode(*, arm: str, run_root: Path, provider: Path, image: str,
                      runtime: str, model: str, base_url: str,
                      api_key_env: str, mcp_python: str,
                      effort: str = MODEL_EFFORT, timeout: float = MODEL_TIMEOUT_S,
                      robase_validation: bool = False,
                      pilot_step_limit: int | None = None) -> dict[str, Any]:
    """Run one v1.3 model arm in real Guest(s); never call this in offline checks."""
    if arm not in ARM_CONDITIONS:
        raise ValueError(f"unknown v1.3 model arm: {arm!r}")
    if effort != MODEL_EFFORT or timeout != MODEL_TIMEOUT_S:
        raise ValueError("the v1.3 triad pins effort=medium and timeout=1200s")
    if pilot_step_limit is not None and arm != "isolated":
        raise ValueError("the diagnostic pilot is Isolated-only; formal arms share the full budget")
    if robase_validation:
        required_robase = ("CODESK_CASE6_V13_GUEST_IMAGE_SHA256",
                           "CODESK_CASE6_V13_RUNTIME_IMAGE_ID",
                           "CODESK_CASE6_V13_OSWORLD_COMMIT",
                           "CODESK_CASE6_V13_OSWORLD_DIFF_SHA256")
        missing_robase = [name for name in required_robase if not os.environ.get(name)]
        if missing_robase:
            raise RuntimeError("read-only-base validation requires frozen image/runtime/OSWorld source pins")
        actual_osworld_identity = osworld_source_identity(provider)
        if not osworld_source_matches(os.environ["CODESK_CASE6_V13_OSWORLD_COMMIT"],
                os.environ["CODESK_CASE6_V13_OSWORLD_DIFF_SHA256"], actual_osworld_identity):
            raise RuntimeError("OSWorld source identity does not match the frozen commit/diff pins")
    else:
        actual_osworld_identity = None
    if not os.environ.get(api_key_env):
        raise RuntimeError(f"provider credential environment variable is missing: {api_key_env}")
    contract = model_contract(arm, model=model, base_url=base_url,
                              api_key_env=api_key_env, mcp_python=mcp_python,
                              pilot_step_limit=pilot_step_limit)
    condition, lock_enabled = ARM_CONDITIONS[arm]
    run_id = run_root.name
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{5,95}", run_id):
        raise ValueError("run-root basename must be a unique safe run_id (6-96 characters)")
    run_root = run_root.resolve()
    if run_root.exists():
        raise FileExistsError(f"run root already exists: {run_root}")
    original_cwd, original_sys_path = Path.cwd(), list(sys.path)
    original_dont_write_bytecode = sys.dont_write_bytecode
    managed_env = ("OSWORLD_DIR", "OSCOMBO_GUEST_IMAGE", "OSCOMBO_RUNTIME_IMAGE",
                   "OSCOMBO_OVERLAY_DIR", "SWCUB_VM_OVERLAY", "OSCOMBO_RUN_LABEL",
                   "OSCOMBO_GUEST_RAM", "OSCOMBO_GUEST_CPUS", "OSCOMBO_VM_READY_TIMEOUT",
                   "PYTHONDONTWRITEBYTECODE")
    original_env = {name: os.environ.get(name) for name in managed_env}
    run_root.mkdir(parents=True, exist_ok=False)
    fixture = run_root / "fixtures"
    fixtures.build_fixture(fixture)
    metadata = {**contract, "run_id": run_id, "fixture_inputs": "public v1.3 Fixture",
                "model_called": False, "started_at": time.time(),
                "guest_validation_status": "actual_run_pending",
                "secret_values_recorded": False,
                "gui_input_lock_path": str(run_root / "gui_input.lock") if lock_enabled else None}
    if robase_validation:
        metadata["guest_resource_policy"] = "case6_readonly_base_v1"
        metadata["osworld_commit_pin"] = os.environ["CODESK_CASE6_V13_OSWORLD_COMMIT"]
        metadata["osworld_commit"] = actual_osworld_identity["commit"]
        metadata["osworld_diff_sha256_pin"] = os.environ["CODESK_CASE6_V13_OSWORLD_DIFF_SHA256"]
        metadata["osworld_diff_sha256"] = actual_osworld_identity["diff_sha256"]
    ledger = RunLedger(run_root, metadata)
    _save_json(run_root / "ownership.json", {"run_id": run_id, "resources": [],
        "cleanup": "only exact owned oscombo.run label and full container ID"})
    store = ProtocolStore(run_root / "collaboration", run_id)
    tokens = {role: secrets.token_urlsafe(32) for role in "AB"}
    server = make_server(store, tokens)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    envs, guests, container_ids = {}, {}, {}
    resource_stop = threading.Event()
    resource_thread = threading.Thread(target=core._sample_guest_resources,
        args=(run_root, container_ids, resource_stop), daemon=True)
    resource_thread.start()
    bridge = None
    relay_server = None
    relay_thread = None
    relay_token_env = "CODESK_RUN_RELAY_TOKEN"
    token_envs: dict[str, str] = {}
    cleanup_errors: list[str] = []
    reopen: list[dict[str, Any]] = []
    outcomes: dict[str, dict[str, Any]] = {}
    reset_evidence: list[dict[str, Any]] = []
    guest_resource_evidence: dict[str, Any] | None = (
        {"boot": {}, "reset": {}} if robase_validation else None)
    try:
        sys.dont_write_bytecode = True
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
        os.environ[relay_token_env] = secrets.token_urlsafe(32)
        relay_server, relay_thread, model_base = _start_allowlisted_relay(
            run_root, base_url, api_key_env, os.environ[relay_token_env])
        for key in (("shared",) if arm != "isolated" else ("A", "B")):
            if robase_validation:
                (run_root / "cache" / key).mkdir(parents=True, exist_ok=True)
            env, guest, cid = core._boot_guest(run_root, run_id, key, image, provider, runtime, ledger)
            envs[key], guests[key], container_ids[key] = env, guest, cid
            if robase_validation:
                container, _ = core._owned_container(env, run_id)
                guest_resource_evidence["boot"][key] = verify_run_owned_guest_resources(
                    container, env, image, run_root, key, stage="boot")
                _save_json(run_root / "guest_resource_evidence.json", guest_resource_evidence)
            shared_pilot._install_v13(guest, fixture, spec.CASE_VERSION)
        screenshot_log_lock = threading.Lock()
        for guest in guests.values():
            _instrument_guest_screenshots(guest, run_root, screenshot_log_lock)
        guest_a = guests.get("shared") or guests["A"]
        guest_b = guests.get("shared") or guests["B"]
        controllers = {"A": guest_a.env.controller, "B": guest_b.env.controller}
        guest_ids = {"A": guest_a.guest_key, "B": guest_b.guest_key}
        bridge = SavedArtifactBridge(
            run_root / "workspace_versions", run_id, spec.TASK_ROOT, controllers, guest_ids,
            case_id=spec.CASE_ID, outputs=spec.OUTPUTS,
            mime_types={role: "application/vnd.oasis.opendocument.spreadsheet" for role in "AB"},
            peer_read_only=True, peer_view_dirs={"A": "incoming/A", "B": "incoming/B"})
        server.workspace_bridge = bridge
        bridge.start()
        a_path = f"{spec.TASK_ROOT}/{spec.OUTPUTS['A']}"
        b_path = f"{spec.TASK_ROOT}/{spec.OUTPUTS['B']}"
        if arm == "isolated":
            # Matching file choices in both topologies; only the desktops differ.
            core._launch(guest_a, "calc", b_path, f"/tmp/{run_id}/peer-order.log", readonly=True)
            shared_pilot._launch_calc(guest_a, a_path, run_id)
            core._launch(guest_b, "calc", a_path, f"/tmp/{run_id}/peer-forecast.log", readonly=True)
            shared_pilot._launch_calc(guest_b, b_path, run_id)
        else:
            shared_pilot._launch_calc(guest_a, b_path, run_id)
            shared_pilot._launch_calc(guest_a, a_path, run_id)
        token_envs = core._model_collaboration_tokens(tokens, ("A", "B"))
        mcp_python_safe = _write_no_bytecode_python(run_root, mcp_python)
        instructions = {
            "A": spec.AGENT_A_INSTRUCTION + f"\nThe open editable output workbook is {a_path}.",
            "B": spec.AGENT_B_INSTRUCTION + f"\nThe open editable output workbook is {b_path}.",
        }
        for role in "AB":
            instructions[role] += (
                "\nSaved role outputs are versioned and copied to the same paths on both desktops. "
                "After saving, use publish_saved_artifact; use list_saved_artifacts/read_messages "
                "for the handoff. The peer file is read-only; do not edit it. Perform task edits "
                "only through Calc GUI and collaboration tools.")
        barrier = threading.Barrier(2)
        def actor(role: str) -> dict[str, Any]:
            guest = guest_a if role == "A" else guest_b
            actor_url = model_base.removesuffix("/v1") + f"/actor/{role}/v1"
            barrier.wait(timeout=60)
            return core._run_model_actor(
                role, guest, instructions[role], run_root, model, actor_url, api_key_env,
                mcp_python_safe, f"http://127.0.0.1:{server.server_port}", token_envs[role],
                max_steps=int(contract["role_budget"][role]["steps"]), effort=MODEL_EFFORT,
                timeout=MODEL_TIMEOUT_S, request_retries=REQUEST_RETRIES,
                relay_client_token_env=relay_token_env, workspace_bridge=True,
                handoff_from=spec.HANDOFF_DEPENDENCIES.get(role), yield_wait=True,
                case_id=spec.CASE_ID,
                gui_input_lock_path=(str(run_root / "gui_input.lock") if lock_enabled else None))
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="case6-v13-actor") as pool:
            futures = {role: pool.submit(actor, role) for role in "AB"}
            for role, future in futures.items():
                outcomes[role] = future.result()

        bridge.stop()
        sync_diagnostics = bridge.diagnostics()
        bridge_ok = not bridge.errors and not sync_diagnostics.get("infrastructure_review_required", True)
        bridge_snapshot = bridge.snapshot()
        _save_json(run_root / "workspace_sync_result.json", {
            "final_versions": bridge_snapshot, "transient_errors": bridge.errors,
            "diagnostics": sync_diagnostics, "verified": bridge_ok})
        bridge = None

        artifact_items, missing = [], []
        for role, guest, path in (("A", guest_a, a_path), ("B", guest_b, b_path)):
            data = guest.env.controller.get_file(path)
            if not data:
                missing.append(role)
                continue
            artifact_items.append({"actor": role, "guest_id": guest.guest_key,
                "guest_path": path, "local_path": f"{role}/{Path(path).name}"})
        _save_json(run_root / "missing_outputs.json", missing)
        artifacts = collect_artifacts(run_root, artifact_items,
            core.GuestFiles({guest.guest_key: guest.env.controller for guest in guests.values()}))
        if len(artifact_items) == 2:
            score = oracle.evaluate(fixture / spec.FIXTURE_NAMES["forecast"],
                run_root / "artifacts/A" / Path(a_path).name,
                fixture / spec.FIXTURE_NAMES["order"],
                run_root / "artifacts/B" / Path(b_path).name)
        else:
            score = {"joint_success": False, "missing_outputs": missing,
                     "score_status": "task_incomplete_missing_actor_artifact"}
        _save_json(run_root / "oracle.json", score)

        for role, guest, path in (("A", guest_a, a_path), ("B", guest_b, b_path)):
            data_before = guest.env.controller.get_file(path)
            if not data_before:
                reopen.append({"role": role, "guest": guest.guest_key, "same_bytes": False,
                               "missing_output": True})
                continue
            try:
                shared_pilot._activate_calc(guest, path)
                guest.actor = "system"
                guest.run_pyautogui("import pyautogui, time; pyautogui.hotkey('ctrl','w'); time.sleep(2)")
                discarded = core._discard_postscore_unsaved_dialog(guest, f"v13-model-reopen-{role}")
                shared_pilot._launch_calc(guest, path, run_id)
                data_after = guest.env.controller.get_file(path)
                reopen.append({"role": role, "guest": guest.guest_key,
                    "same_bytes": data_before == data_after,
                    "sha256": hashlib.sha256(data_after or b"").hexdigest(),
                    "discarded_uncommitted_buffer_after_scoring": discarded})
            except Exception as exc:
                reopen.append({"role": role, "guest": guest.guest_key, "same_bytes": False,
                    "saved_sha256": hashlib.sha256(data_before).hexdigest(),
                    "postscore_error": f"{type(exc).__name__}: {exc}"})
        _save_json(run_root / "reopen_evidence.json", reopen)
        postscore_ok = shared_pilot._postscore_lifecycle_ok(reopen)

        protocol_events = _read_jsonl(run_root / "collaboration" / "events.jsonl")
        handoff = audit_model_handoff(run_root, bridge_snapshot, protocol_events)
        _save_json(run_root / "handoff_audit.json", handoff)
        relay_result = relay_transport.audit(run_root)
        _save_json(run_root / "relay_transport_audit.json", relay_result)
        boundary = audit_actor_tool_boundary(run_root)
        _save_json(run_root / "actor_tool_boundary_audit.json", boundary)

        for key, env in envs.items():
            old_id = container_ids[key]
            core._verify_container(old_id, run_id)
            os.environ["OSCOMBO_OVERLAY_DIR"] = str(run_root / "overlay" / key)
            os.environ["SWCUB_VM_OVERLAY"] = str(run_root / "overlay" / key)
            os.environ["OSCOMBO_RUN_LABEL"] = run_id
            env.is_environment_used = True
            env.reset()
            new_container, labels = core._owned_container(env, run_id)
            container_ids[key] = new_container.id
            resource_row = None
            if robase_validation:
                resource_row = verify_run_owned_guest_resources(
                    new_container, env, image, run_root, key, stage="reset")
                guest_resource_evidence["reset"][key] = resource_row
                _save_json(run_root / "guest_resource_evidence.json", guest_resource_evidence)
            if new_container.id == old_id or not core._missing_container(old_id):
                raise RuntimeError("reset did not replace the run-owned v1.3 Guest")
            core._shell(guests[key],
                f"test ! -e {shlex.quote(spec.TASK_ROOT)} && ! pgrep -x soffice.bin >/dev/null")
            reset_row = {"guest": key, "old": old_id, "new": new_container.id,
                         "workspace_clean": True, "labels": labels}
            if resource_row is not None:
                reset_row["guest_resources_verified"] = resource_row["verified"]
            reset_evidence.append(reset_row)
        _save_json(run_root / "reset_evidence.json", reset_evidence)
        reset_ok = (len(reset_evidence) == len(envs)
                    and all(row["workspace_clean"] and
                            (not robase_validation or row.get("guest_resources_verified") is True)
                            for row in reset_evidence))
        status = map_model_result(oracle_result=score, actor_results=outcomes,
            handoff=handoff, bridge_ok=bridge_ok, relay_audit=relay_result,
            actor_tool_audit=boundary, postscore_lifecycle_ok=postscore_ok, reset_ok=reset_ok)
        elapsed = time.time() - float(metadata["started_at"])
        relay_events = _read_jsonl(run_root / "codex_relay_events.jsonl")
        ledger.metadata["model_called"] = bool(relay_events)
        ledger.metadata_path.write_text(json.dumps(ledger.metadata, indent=2, sort_keys=True) + "\n")
        execution_metrics = summarize_execution_metrics(run_root, outcomes,
                                                        float(metadata["started_at"]))
        overlap = compute_overlap_summary(
            relay_events,
            _read_jsonl(run_root / "gui_actions.jsonl"),
            _read_jsonl(run_root / "actor_lifecycle.jsonl"), outcomes)
        result = {"run_id": run_id, "case_id": spec.CASE_ID,
            "case_version": spec.CASE_VERSION, "arm": arm, "condition": condition,
            "model": model, "model_called": bool(relay_events), "actor_results": outcomes,
            "wall_clock_interval_overlap_s": overlap["wall_clock_interval_overlap_s"],
            "active_overlap": overlap,
            "model_usage": _usage_by_actor(run_root), "oracle": score,
            "execution_metrics": execution_metrics,
            "artifact_manifest": artifacts, "handoff": handoff,
            "bridge_verified": bridge_ok, "relay_transport_valid": relay_result.get("valid"),
            "actor_tool_boundary_valid": boundary.get("valid"), "reopen": reopen,
            "postscore_lifecycle_ok": postscore_ok, "reset": reset_evidence,
            "elapsed_s": round(elapsed, 3), "status": status,
            "visual_review_required": True}
        if guest_resource_evidence is not None:
            result["guest_resource_evidence"] = guest_resource_evidence
            result["guest_resource_policy"] = "case6_readonly_base_v1"
        _save_json(run_root / "result.json", result)
        return result
    finally:
        resource_stop.set()
        resource_thread.join(timeout=10)
        if bridge is not None:
            try:
                bridge.stop()
            except Exception as exc:
                with (run_root / "workspace_sync_errors.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps({"error_type": type(exc).__name__}) + "\n")
        for name in (*token_envs.values(), relay_token_env):
            os.environ.pop(name, None)
        for key, env in envs.items():
            cid = container_ids.get(key)
            if not cid:
                continue
            try:
                core._verify_container(cid, run_id)
                env.close()
                if not core._missing_container(cid):
                    raise RuntimeError(f"owned Guest {cid} remains after close")
            except Exception as exc:
                cleanup_errors.append(f"{key}: {type(exc).__name__}: {exc}")
                with (run_root / "cleanup_errors.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps({"guest": key, "error_type": type(exc).__name__}) + "\n")
        if relay_server is not None:
            relay_server.shutdown()
            relay_server.server_close()
        if relay_thread is not None:
            relay_thread.join(timeout=5)
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)
        for name, value in original_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        sys.path[:] = original_sys_path
        os.chdir(original_cwd)
        sys.dont_write_bytecode = original_dont_write_bytecode
        if cleanup_errors:
            raise RuntimeError("run-owned Guest cleanup incomplete: " + "; ".join(cleanup_errors))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", required=True, choices=tuple(ARM_CONDITIONS))
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--provider", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key-env", required=True)
    parser.add_argument("--mcp-python", required=True)
    parser.add_argument("--pilot-step-limit", type=int, default=None,
                        help=(f"Isolated-only diagnostic cap ({PILOT_STEP_MIN}-{PILOT_STEP_MAX} "
                              "tool steps per role); omit for the unchanged 18-step formal budget"))
    parser.add_argument("--robase-validation", action="store_true",
                        help="enable the versioned read-only-base Guest/cache/runtime checks")
    args = parser.parse_args(argv)
    try:
        result = run_model_episode(arm=args.arm, run_root=args.run_root,
            provider=args.provider.resolve(), image=args.image, runtime=args.runtime,
            model=args.model, base_url=args.base_url, api_key_env=args.api_key_env,
            mcp_python=args.mcp_python, robase_validation=args.robase_validation,
            pilot_step_limit=args.pilot_step_limit)
    except Exception as exc:
        secret = os.environ.get(args.api_key_env, "")
        error_text = str(exc)
        trace_text = traceback.format_exc()
        if secret:
            error_text = error_text.replace(secret, "[REDACTED]")
            trace_text = trace_text.replace(secret, "[REDACTED]")
        relay_log = args.run_root / "codex_relay_events.jsonl"
        model_called = any(row.get("started_at") for row in _read_jsonl(relay_log))
        failure = {"status": "INVALID_INFRA_OR_RUNNER_ERROR", "run_id": args.run_root.name,
                   "case_version": spec.CASE_VERSION,
                   "model_runner_version": MODEL_RUNNER_VERSION,
                   "execution_mode": "diagnostic_pilot" if args.pilot_step_limit is not None else "formal",
                   "pilot_step_limit": args.pilot_step_limit,
                   "error_type": type(exc).__name__, "error": error_text,
                   "traceback": trace_text, "model_called": model_called,
                   "secret_value_recorded": False}
        if args.run_root.exists():
            _save_json(args.run_root / "failure.json", failure)
        print(json.dumps(failure, indent=2), file=sys.stderr)
        raise SystemExit(3)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 2)


if __name__ == "__main__":
    main()
