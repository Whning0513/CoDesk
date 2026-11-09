#!/usr/bin/env python3
"""Run no-model EDIT-1 Writer controls on real OSWorld Native-QEMU Guests."""
from __future__ import annotations

import argparse
import base64
import json
import os
import shlex
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from oscombo.collab.edit_mode_handoff import CASE_ID, CASE_VERSION
from oscombo.collab.edit_mode_handoff.fixtures import build_fixture
from oscombo.collab.edit_mode_handoff.oracle import evaluate
from oscombo.collab.edit_mode_handoff.spec import PUBLIC_FILE
from oscombo.collab.data_to_deck import live_pilot as pilot
from oscombo.collab.data_to_deck.provenance import RunLedger
from scripts import run_calc_locale_handoff_guest_control as qemu

_ACTION_LOCK: threading.Lock | None = None


def _action(guest: pilot.LoggedGuest, actor: str, code: str) -> None:
    if _ACTION_LOCK is None:
        qemu._action(guest, actor, code)
    else:
        with _ACTION_LOCK:
            qemu._action(guest, actor, code)


def _stage(guest: pilot.LoggedGuest, fixture: Path, guest_dir: str, output_name: str) -> str:
    guest.actor = "system"
    pilot._shell(guest, f"mkdir -p {shlex.quote(guest_dir)}", timeout=20)
    raw = (fixture / "public" / PUBLIC_FILE).read_bytes()
    encoded = base64.b64encode(raw).decode("ascii")
    path = f"{guest_dir}/{output_name}"
    pilot._shell(guest, f"printf %s {shlex.quote(encoded)} | base64 -d > {shlex.quote(path)}",
                 timeout=30)
    return path


def _open_writer(guest: pilot.LoggedGuest, path: str, profile: str) -> None:
    guest.actor = "system"
    pilot._shell(guest, f"mkdir -p {shlex.quote(profile)}", timeout=20)
    command = (f"nohup soffice -env:UserInstallation=file://{profile} --writer "
               f"--norestore --nolockcheck {shlex.quote(path)} "
               ">/tmp/edit-mode-writer.log 2>&1 </dev/null & "
               "for i in $(seq 1 180); do wmctrl -l 2>/dev/null | grep -Fq release_notice && break; sleep 1; done; "
               "wmctrl -lGx 2>&1; wmctrl -a release_notice 2>&1; sleep 2; "
               "xdotool getactivewindow getwindowname 2>&1; tail -n 40 /tmp/edit-mode-writer.log 2>&1")
    state = pilot._shell(guest, qemu._with_x11(command), timeout=200)
    output = state.get("output", "")
    if "release_notice" not in output:
        raise RuntimeError(f"Writer document did not open: {output[-1600:]}")
    time.sleep(65)
    _action(guest, "system",
        "pyautogui.press('enter'); time.sleep(3); "
        "pyautogui.click(1848,187); time.sleep(1); "
        "pyautogui.click(650,400); time.sleep(0.5)")


def _prepare_anchor(guest: pilot.LoggedGuest, actor: str) -> None:
    _action(guest, actor,
        "pyautogui.click(650,400); time.sleep(0.3); pyautogui.hotkey('ctrl','home'); "
        "pyautogui.press('right', presses=25, interval=0.03); time.sleep(0.4)")


def _edit_a(guest: pilot.LoggedGuest, actor: str) -> None:
    qemu._action(guest, actor,
        "pyautogui.write('READY ', interval=0.08); time.sleep(0.5); pyautogui.hotkey('ctrl','s'); time.sleep(2)")


def _edit_b(guest: pilot.LoggedGuest, actor: str, switch_to_overwrite: bool = True) -> None:
    action = ("pyautogui.click(650,400); pyautogui.hotkey('ctrl','home'); "
              "pyautogui.press('down'); pyautogui.press('right', presses=15, interval=0.03); ")
    if switch_to_overwrite:
        action += "pyautogui.press('insert'); "
    action += ("pyautogui.write('AB12', interval=0.08); time.sleep(0.5); "
               "pyautogui.hotkey('ctrl','s'); time.sleep(2); "
               "pyautogui.hotkey('ctrl','home'); "
               "pyautogui.press('right', presses=25, interval=0.03); time.sleep(0.5)")
    _action(guest, actor, action)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="edit-mode-handoff-guest-control-"
                        + time.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6])
    parser.add_argument("--artifact-parent", type=Path, default=qemu.DEFAULT_ARTIFACT_PARENT)
    parser.add_argument("--image", type=Path, default=qemu.DEFAULT_IMAGE)
    parser.add_argument("--osworld", type=Path, default=qemu.DEFAULT_OSWORLD)
    parser.add_argument("--cpus", type=int, default=4)
    parser.add_argument("--shared-only", action="store_true",
                        help="run the shared scripted arm; link an existing isolated control via --isolated-baseline")
    parser.add_argument("--per-action-lock", action="store_true",
                        help="serialize each GUI tool invocation in the shared control")
    parser.add_argument("--isolated-baseline", default=None)
    args = parser.parse_args()
    global _ACTION_LOCK
    if args.per_action_lock:
        _ACTION_LOCK = threading.Lock()
    root = args.artifact_parent.expanduser().resolve() / args.run_id
    if root.exists():
        raise FileExistsError(root)
    for name in ("screenshots", "cache", "native-qemu", "artifacts", "workspace"):
        (root / name).mkdir(parents=True, exist_ok=True)
    evaluator_fixture = root / "evaluator_fixture"
    evaluator_fixture.mkdir()
    build_fixture(evaluator_fixture)
    qemu_prefix = qemu._stage_qemu_prefix(
        root / "native-qemu" / "runtime-prefix", qemu.DEFAULT_QEMU_ROOT.resolve())
    qemu._configure_native(args.run_id, root / "native-qemu", args.image.resolve(),
                           args.osworld.resolve(), qemu_prefix)
    os.environ["OSCOMBO_NATIVE_CPUS"] = str(args.cpus)
    os.environ["OSCOMBO_NATIVE_E1000_ROMFILE"] = ""
    ledger = RunLedger(root, {"run_id": args.run_id, "case_id": CASE_ID,
                              "case_version": CASE_VERSION,
                              "scope": "real Guest scripted GUI control; no model/API"})
    envs: dict[str, object] = {}
    guests: dict[str, pilot.LoggedGuest] = {}
    result: dict = {"run_id": args.run_id, "case_id": CASE_ID,
                    "case_version": CASE_VERSION, "model_used": False,
                    "status": "running", "setup": {}, "arms": {}, "cleanup": {}}
    try:
        if not args.shared_only:
            isolated_root = root / "workspace" / "isolated"
            isolated_root.mkdir()
            for actor in ("A", "B"):
                envs[actor], guests[actor], setup = qemu._start_guest(
                    actor, args.run_id, root, args.image.resolve(), ledger)
                result["setup"][actor] = setup
                result["setup"][actor]["desktop_ready"] = qemu._wait_for_desktop_ready(
                    guests[actor], root, actor)
            paths = {
                "A": _stage(guests["A"], evaluator_fixture, f"/tmp/{args.run_id}/A", "release_notice_A.fodt"),
                "B": _stage(guests["B"], evaluator_fixture, f"/tmp/{args.run_id}/B", "release_notice_B.fodt"),
            }
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(_open_writer, guests[actor], path,
                                       f"/tmp/{args.run_id}/profile-{actor}")
                           for actor, path in paths.items()]
                for future in futures:
                    future.result()
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(_prepare_anchor, guests["A"], "A"),
                           pool.submit(_edit_b, guests["B"], "B")]
                for future in futures:
                    future.result()
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(_edit_a, guests["A"], "A"),
                           pool.submit(_save_only, guests["B"], "B")]
                for future in futures:
                    future.result()
            isolated_artifacts = root / "artifacts" / "isolated"
            isolated_artifacts.mkdir()
            qemu._collect(envs["A"], paths["A"], isolated_artifacts / "release_notice_A.fodt")
            qemu._collect(envs["B"], paths["B"], isolated_artifacts / "release_notice_B.fodt")
            result["arms"]["isolated"] = evaluate(isolated_artifacts, "isolated")
            for actor in ("A", "B"):
                qemu._close_guest(actor, envs.pop(actor), result["cleanup"])
                guests.pop(actor, None)
        elif args.isolated_baseline:
            result["isolated_baseline_run_id"] = args.isolated_baseline

        envs["shared"], guests["shared"], setup = qemu._start_guest(
            "SHARED", args.run_id, root, args.image.resolve(), ledger)
        result["setup"]["shared"] = setup
        result["setup"]["shared"]["desktop_ready"] = qemu._wait_for_desktop_ready(
            guests["shared"], root, "SHARED")
        shared_dir = f"/tmp/{args.run_id}/shared"
        shared_path = _stage(guests["shared"], evaluator_fixture, shared_dir, "release_notice.fodt")
        _open_writer(guests["shared"], shared_path, f"/tmp/{args.run_id}/profile-shared")
        _prepare_anchor(guests["shared"], "A")
        _edit_b(guests["shared"], "B")
        _edit_a(guests["shared"], "A")
        shared_artifacts = root / "artifacts" / "shared"
        shared_artifacts.mkdir()
        qemu._collect(envs["shared"], shared_path, shared_artifacts / "release_notice.fodt")
        result["arms"]["shared"] = evaluate(shared_artifacts, "shared")
        if args.per_action_lock:
            result["arms"]["shared"]["topology"] = "shared_per_action_lock"
            result["arms"]["shared"]["per_action_lock"] = {
                "enabled": True, "scope": "one LoggedGuest GUI tool invocation",
                "max_concurrent_tool_invocations": 1,
            }
        result["arms"]["shared"]["attribution"] = {
            "same_guest_and_writer_document": True,
            "B_switched_to_overwrite": True,
            "A_executed_stale_insertion_plan_without_reobservation": True,
            "overwrite_signature_observed": (
                result["arms"]["shared"].get("observed_lines", [None])[0]
                == "Release status: STATUS | READY OR-REVIEW"),
            "causal_interleaving": ["A observed insertion anchor", "B changed code under OVR",
                                    "A replayed READY insertion at stale anchor"],
        }
        result["arms"]["shared"]["attribution"]["causal_failure_attributed"] = (
            result["arms"]["shared"]["actor_success"]["B"]
            and not result["arms"]["shared"]["actor_success"]["A"]
            and result["arms"]["shared"]["attribution"]["overwrite_signature_observed"])
        qemu._close_guest("SHARED", envs.pop("shared"), result["cleanup"])
        guests.pop("shared", None)
        shared_pass = (
            result["arms"]["shared"]["actor_success"]["B"]
            and not result["arms"]["shared"]["actor_success"]["A"]
            and result["arms"]["shared"]["attribution"]["causal_failure_attributed"])
        if args.shared_only:
            result["status"] = "shared_control_passed" if shared_pass else "shared_control_not_passed"
            if args.per_action_lock:
                result["status"] = "shared_lock_control_passed" if shared_pass else "shared_lock_control_not_passed"
        else:
            result["status"] = "controls_pass" if (
            result["arms"]["isolated"]["joint_success"]
            and shared_pass) else "controls_not_passed"
    except BaseException as exc:
        result["status"] = "control_error"
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        for key, env in list(envs.items()):
            qemu._close_guest(key, env, result["cleanup"])
        qemu._json(root / "report.json", result)
    print(json.dumps({"run_id": args.run_id, "status": result["status"],
                      "artifact_root": str(root), "arms": result.get("arms"),
                      "cleanup": result.get("cleanup")}, ensure_ascii=False, indent=2))
    return 0 if result["status"] in ("controls_pass", "shared_control_passed",
                                      "shared_lock_control_passed") else 1


def _save_only(guest: pilot.LoggedGuest, actor: str) -> None:
    qemu._action(guest, actor, "pyautogui.hotkey('ctrl','s'); time.sleep(2)")


if __name__ == "__main__":
    raise SystemExit(main())
