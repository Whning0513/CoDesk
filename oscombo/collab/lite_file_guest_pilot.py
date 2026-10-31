"""Real OSWorld Guest adapter for the short browser and file-manager handoffs.

The existing Guest, Codex harness, collaboration server, artifact bridge and
owned-QEMU lifecycle are reused. This module supplies only case-specific app
setup, scripted controls and artifact scoring.
"""
from __future__ import annotations

import argparse
import base64
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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from oscombo.collab.data_to_deck import live_pilot as core
from oscombo.collab.data_to_deck.collab_tools import CollaborationClient
from oscombo.collab.data_to_deck.protocol import ProtocolStore, make_server
from oscombo.collab.data_to_deck.provenance import RunLedger, collect_artifacts
from oscombo.collab.data_to_deck.workspace_bridge import SavedArtifactBridge


WORKSPACE_ASSEMBLY_CASES = {"workspace_assembly", "workspace_assembly_v1p2", "workspace_assembly_v2"}


def _profile(case: str):
    if case == "build_verify":
        from oscombo.collab.build_and_verify_lite_v1 import spec, fixtures, oracle
    elif case == "workspace_assembly":
        from oscombo.collab.workspace_assembly_lite_v1 import spec, fixtures, oracle
    elif case == "workspace_assembly_v1p2":
        from oscombo.collab.workspace_assembly_lite_v1p2 import spec, fixtures, oracle
    elif case == "workspace_assembly_v2":
        from oscombo.collab.workspace_assembly_lite_v2 import spec, fixtures, oracle
    elif case == "model_review":
        from oscombo.collab.model_and_review_lite_v1 import spec, fixtures, oracle
    else:
        raise ValueError(f"unknown Lite case: {case}")
    return spec, fixtures, oracle


def _guest_script(guest, script: str, timeout: int = 45):
    return core._shell(guest, script, timeout=timeout)


def _install(guest, fixture: Path, task_root: str, case: str, spec):
    names = spec.FIXTURE_NAMES
    commands = [f"test ! -e {shlex.quote(task_root)}",
                f"mkdir -p {shlex.quote(task_root + '/input')} "
                f"{shlex.quote(task_root + '/outputs/agent_A')} "
                f"{shlex.quote(task_root + '/outputs/agent_B')} "
                f"{shlex.quote(task_root + '/incoming')}"]
    if case == "workspace_assembly_v2":
        commands.append(f"mkdir -p {shlex.quote(task_root + '/' + spec.PEER_VIEW_DIRS['A'])}")
    for name in names.values():
        encoded = base64.b64encode((fixture / name).read_bytes()).decode("ascii")
        commands.append(f"printf %s {shlex.quote(encoded)} | base64 -d > "
                        f"{shlex.quote(task_root + '/input/' + name)}")
    commands.append(f"chmod -R a-w {shlex.quote(task_root + '/input')}")
    if case == "build_verify":
        for role, key in (("A", "source"), ("B", "qa")):
            commands.append(f"cp {shlex.quote(task_root + '/input/' + names[key])} "
                            f"{shlex.quote(task_root + '/' + spec.OUTPUTS[role])}")
            commands.append(f"chmod u+w {shlex.quote(task_root + '/' + spec.OUTPUTS[role])}")
    elif case in WORKSPACE_ASSEMBLY_CASES:
        commands.append(f"cp {shlex.quote(task_root + '/input/' + names['asset'])} "
                        f"{shlex.quote(task_root + '/incoming/' + names['asset'])}")
        commands.append(f"chmod u+w {shlex.quote(task_root + '/incoming/' + names['asset'])}")
        commands.append(f"cp {shlex.quote(task_root + '/input/' + names['report'])} "
                        f"{shlex.quote(task_root + '/' + spec.OUTPUTS['B'])}")
        commands.append(f"chmod u+w {shlex.quote(task_root + '/' + spec.OUTPUTS['B'])}")
    elif case == "model_review":
        for role, key in (("A", "scene"), ("B", "report")):
            commands.append(f"cp {shlex.quote(task_root + '/input/' + names[key])} "
                            f"{shlex.quote(task_root + '/' + spec.OUTPUTS[role])}")
            commands.append(f"chmod u+w {shlex.quote(task_root + '/' + spec.OUTPUTS[role])}")
    _guest_script(guest, "set -e\n" + "\n".join(commands), timeout=60)


def _launch(guest, app: str, path: str, run_id: str):
    """Setup/reopen only. Never used to arbitrate model-time GUI focus."""
    if app == "writer":
        return core._launch(guest, "writer", path, f"/tmp/{run_id}/writer.log")
    choices = {
        "editor": "command -v gedit || command -v gnome-text-editor || command -v mousepad",
        "browser": "command -v google-chrome || command -v chromium-browser || command -v chromium",
        "files": "command -v nautilus || command -v thunar",
        "blender": "command -v blender",
    }
    if app not in choices:
        raise ValueError(app)
    quoted = shlex.quote(path)
    check = _guest_script(guest, choices[app], timeout=15)
    binary = (check.get("output") or "").strip().splitlines()[-1]
    if not binary.startswith("/"):
        raise RuntimeError(f"Guest {app} application not found")
    args = ("--no-first-run --no-default-browser-check " if app == "browser" else
            "--disable-autoexec " if app == "blender" else "")
    uri = "file://" + path if app == "browser" else path
    _guest_script(guest, f"mkdir -p /tmp/{shlex.quote(run_id)}; "
                  f"nohup {shlex.quote(binary)} {args}{shlex.quote(uri)} "
                  f">/tmp/{shlex.quote(run_id)}/{app}.log 2>&1 </dev/null &", timeout=15)
    deadline = time.monotonic() + (300 if app == "blender" else 120)
    hint = ("OrderDesk Lite" if app == "browser" else
            "Blender" if app == "blender" else Path(path).name)
    while time.monotonic() < deadline:
        active = guest.active_window() or ""
        shot = guest.screenshot(patience=45)
        if hint.casefold() in active.casefold() and core._desktop_frame_ready(shot):
            dest = guest.root / "screenshots" / f"{guest.guest_key}-{app}-ready-{time.time_ns()}.png"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(shot)
            return
        time.sleep(3)
    raise RuntimeError(f"{app} did not become the visible Guest window: {hint}")


def _postscore_lifecycle_ok(reopen: list[dict]) -> bool:
    """Distinguish an absent task output from failure to reopen a saved one."""
    return len(reopen) == 2 and all(
        item.get("missing_output") is True or
        (item.get("same_bytes") is True and
         item.get("gui_reopen") != "skipped_unsaved_buffer") for item in reopen)


def _result_exit_code(status: str) -> int:
    """Preserve task failure vs. invalid-run distinction for shell drivers."""
    return {"PASS": 0, "FAIL": 2}.get(status, 3)


def _maximize_case7_files(guest):
    """Set the same broad Files viewport before either model Actor starts."""
    def geometry():
        # wmctrl -lG: id, desktop, x, y, width, height, host, title.
        result = _guest_script(guest, "wmctrl -lG", timeout=15)
        incoming = [line.split() for line in (result.get("output") or "").splitlines()
                    if line.rstrip().endswith(" incoming")]
        if not incoming or len(incoming[-1]) < 8:
            raise RuntimeError("Case 7 Files window not found during maximize")
        row = incoming[-1]
        if not re.fullmatch(r"0x[0-9a-fA-F]+", row[0]):
            raise RuntimeError("Case 7 Files window ID is invalid")
        return row[0], int(row[4]), int(row[5])

    window_id, width, height = geometry()
    attempts = [{"method": "initial", "width": width, "height": height}]
    for _ in range(2):
        if width >= 1500 and height >= 800:
            break
        # Select the exact Nautilus window, then request both maximize states.
        _guest_script(guest,
            f"wmctrl -i -a {shlex.quote(window_id)}; "
            f"wmctrl -i -r {shlex.quote(window_id)} -b add,maximized_vert,maximized_horz; "
            "sleep 3", timeout=15)
        _, width, height = geometry()
        attempts.append({"method": "wmctrl_exact_id", "width": width, "height": height})
    if width < 1500 or height < 800:
        # GNOME can ignore a WM state request just after the window appears.
        # Use its standard maximize shortcut in the same pre-Actor setup for
        # both desktop topologies.
        guest.actor = "system"
        guest.run_pyautogui("import pyautogui, time; "
                            "pyautogui.hotkey('winleft','up'); time.sleep(3)")
        _, width, height = geometry()
        attempts.append({"method": "gui_super_up", "width": width, "height": height})
    (guest.root / "case7_files_setup.json").write_text(json.dumps(attempts, indent=2) + "\n")
    if width < 1500 or height < 800:
        shot = guest.screenshot(patience=45)
        (guest.root / "screenshots" / f"{guest.guest_key}-files-unmaximized.png").write_bytes(shot)
        raise RuntimeError(f"Case 7 Files window was not maximized: {width}x{height}")
    shot = guest.screenshot(patience=45)
    (guest.root / "screenshots" / f"{guest.guest_key}-files-maximized.png").write_bytes(shot)


def _activate(guest, app: str, path: str):
    if app == "writer":
        return core._activate_ready_document(guest, path, "lite-file-reopen")
    hint = ("OrderDesk Lite" if app == "browser" else
            "Blender" if app == "blender" else Path(path).name)
    _guest_script(guest, f"wmctrl -a {shlex.quote(hint)}", timeout=15)
    if hint.casefold() not in (guest.active_window() or "").casefold():
        raise RuntimeError(f"cannot activate {hint}")


def _restore_closed_case7_writer(guest, path: str, run_id: str) -> bool:
    """Restore only a demonstrably closed saved Writer after model execution."""
    try:
        _activate(guest, "writer", path)
        return False
    except RuntimeError:
        listing = _guest_script(guest, "wmctrl -l", timeout=15)
        if listing.get("status") != "success":
            raise RuntimeError("could not verify Writer window list")
        if Path(path).name.casefold() in (listing.get("output") or "").casefold():
            raise RuntimeError("Writer window exists but activation failed")
        _launch(guest, "writer", path, run_id)
        _activate(guest, "writer", path)
        return True


def _case7_control_retry_open(guest, run_root: Path, instruction: str, case_id: str) -> bool:
    """Retry a still-open GTK file picker once, only for scripted controls."""
    if (guest.active_window() or "").strip().casefold() != "open":
        return False
    import struct
    shot = guest.screenshot(patience=45)
    if not shot.startswith(b"\x89PNG\r\n\x1a\n") or struct.unpack(">II", shot[16:24]) != (1920, 1080):
        raise RuntimeError("cannot safely retry Case 7 Open dialog at unknown geometry")
    path = run_root / "screenshots" / "control_B_open_retry_before.png"
    path.write_bytes(shot)
    # The guest fixture uses the 1920x1080 GTK file picker; this is the green
    # Open button. The explicit screenshot/action trace keeps the retry visible.
    result = core._run_actor("B", guest, instruction,
        ["import pyautogui, time; pyautogui.click(1550, 164); time.sleep(6)", "DONE"],
        run_root, max_steps=25, case_id=case_id)
    (run_root / "control_B_open_retry.json").write_text(json.dumps({
        "reason": "file chooser remained open after path submission",
        "before_screenshot": str(path.relative_to(run_root)), "trace_path": result.get("trace_path"),
        "status": result.get("status"), "time": time.time()}, indent=2) + "\n")
    if result.get("status") != "done":
        raise RuntimeError("scripted B Open button retry failed")
    return True


def _stop_bridge_before_cleanup(bridge, case, run_root, run_id, container_ids, cleanup_errors):
    """Return True only when live bridge access requires deferring Guests."""
    if bridge is None:
        return False
    try:
        bridge.stop()
        return False
    except Exception as exc:
        core._append(run_root / "workspace_sync_errors.jsonl", {"error": str(exc), "time": time.time()})
        cleanup_errors.append(f"bridge stop failed: {type(exc).__name__}: {exc}")
        if case != "workspace_assembly_v2" or not bridge._thread or not bridge._thread.is_alive():
            return False
        # Keep the lease and Guests until the worker's process has exited.
        from oscombo.collab.workspace_assembly_lite_v2.deferred_cleanup import write_pending
        try:
            write_pending(run_root, run_id, dict(container_ids), str(exc))
        except Exception as pending_exc:
            cleanup_errors.append(f"cannot write deferred cleanup record: {pending_exc}")
        return True


def _editor_has_unsaved_buffer(title: str, path: str) -> bool:
    return f"*{Path(path).name}".casefold() in title.casefold()


def _activate_editor_tab(guest, role: str, shared: bool):
    """Scripted setup for the Text Editor's two tabs on one Shared desktop."""
    if not shared:
        return
    # GNOME Text Editor reuses one window for both files. The A tab is opened
    # last during setup; after activating that window, choose the requested
    # tab with a real GUI click. Model actors receive no such intervention.
    _guest_script(guest, "wmctrl -a orderdesk.html || wmctrl -a qa_note.txt", timeout=15)
    guest.actor = "system"
    guest.run_pyautogui("import pyautogui, time; pyautogui.click(760,193); time.sleep(1)"
                         if role == "A" else
                         "import pyautogui, time; pyautogui.click(300,193); time.sleep(1)")


def _scripted_actions(case: str, role: str, task_root: str, fixtures, negative: bool) -> list[str]:
    if case == "workspace_assembly_v2":
        from oscombo.collab.workspace_assembly_lite_v2 import scripted
        if role == "A":
            return scripted.a_move(task_root)
        if role == "B":
            return scripted.b_finish("WRONG-00" if negative else fixtures.DEFAULT_TAG)
        raise ValueError((case, role))
    if case == "build_verify" and role == "A":
        corrected = fixtures.source_html().replace('value="delievered"',
                                                   'value="delievered"' if negative else 'value="delivered"')
        return ["import pyautogui, time; pyautogui.hotkey('ctrl','a'); time.sleep(1)",
                f"import pyautogui, time; pyautogui.write({corrected!r}, interval=0.002); time.sleep(2)",
                "import pyautogui, time; pyautogui.hotkey('ctrl','s'); time.sleep(3)", "DONE"]
    if case == "build_verify" and role == "B":
        note = ("Query: North\nStatus: Delivered\nVisible order IDs: " +
                ("none" if negative else "OD-104") + "\nSaved source: orderdesk.html\n")
        return [
            "import pyautogui, time; pyautogui.hotkey('ctrl','l'); time.sleep(2)",
            f"import pyautogui, time; pyautogui.write({('file://' + task_root + '/outputs/agent_A/orderdesk.html')!r}, 0.05); time.sleep(1); pyautogui.press('enter'); time.sleep(4)",
            "import pyautogui, time; pyautogui.click(680,268); pyautogui.write('North', 0.1); time.sleep(1)",
            "import pyautogui, time; pyautogui.click(1050,268); pyautogui.press('end'); pyautogui.press('enter'); time.sleep(1)",
            "import pyautogui, time; pyautogui.click(1180,268); time.sleep(3)",
            "import pyautogui, time; pyautogui.hotkey('ctrl','a'); time.sleep(1)",
            f"import pyautogui, time; pyautogui.write({note!r}, 0.03); time.sleep(1)",
            "import pyautogui, time; pyautogui.hotkey('ctrl','s'); time.sleep(3)", "DONE"]
    if case in WORKSPACE_ASSEMBLY_CASES and role == "A":
        actions = [
            "import pyautogui, time; pyautogui.hotkey('ctrl','a'); time.sleep(2)",
            "import pyautogui, time; pyautogui.hotkey('ctrl','x'); time.sleep(2)",
            f"import pyautogui, time; pyautogui.hotkey('ctrl','l'); pyautogui.write({(task_root + '/outputs/agent_A')!r}, 0.01); pyautogui.press('enter'); time.sleep(2)",
            "import pyautogui, time; pyautogui.hotkey('ctrl','v'); time.sleep(3)"]
        if case == "workspace_assembly_v1p2":
            actions += [
                "import pyautogui, time; pyautogui.hotkey('ctrl','a'); pyautogui.press('enter'); time.sleep(8)",
                "import pyautogui, time; pyautogui.hotkey('alt','f4'); time.sleep(2)"]
        return actions + ["DONE"]
    if case in WORKSPACE_ASSEMBLY_CASES and role == "B":
        sentence = ("The delivered inspection attachment is inspection_note.txt with inspection tag " +
                    ("WRONG." if negative else "RIVER-27."))
        text = "Aurora Supply Handoff\n" + sentence + "\nPrepared for operations review."
        return ["import pyautogui, time; pyautogui.hotkey('ctrl','a'); time.sleep(1)",
                f"import pyautogui, time; pyautogui.write({text!r}, 0.03); time.sleep(2)",
                "import pyautogui, time; pyautogui.hotkey('ctrl','s'); time.sleep(3)", "DONE"]
    if case == "model_review" and role == "A":
        factor = "1.083333333" if negative else "1.216666667"
        return [
            "import pyautogui, time; pyautogui.moveTo(900,500); pyautogui.press('esc'); time.sleep(1)",
            f"import pyautogui, time; pyautogui.press('s'); pyautogui.hotkey('shift','z'); pyautogui.write('{factor}', 0.1); pyautogui.press('enter'); time.sleep(2)",
            "import pyautogui, time; pyautogui.hotkey('ctrl','s'); time.sleep(4)", "DONE"]
    if case == "model_review" and role == "B":
        text = ("Shade width: 1.30 m\nRadial clearance: 0.40 m\nVerdict: PASS\n" if negative else
                "Shade width: 1.46 m\nRadial clearance: 0.48 m\nVerdict: PASS\n")
        return ["import pyautogui, time; pyautogui.hotkey('ctrl','a'); time.sleep(1)",
                f"import pyautogui, time; pyautogui.write({text!r}, 0.02); time.sleep(1)",
                "import pyautogui, time; pyautogui.hotkey('ctrl','s'); time.sleep(3)", "DONE"]
    raise ValueError((case, role))


def _audit_case7_scripted_delivered_read(run_root: Path) -> dict:
    """Require the control's A to view the moved note through a GUI app."""
    action_path = run_root / "gui_actions.jsonl"
    actions = [json.loads(line) for line in action_path.read_text().splitlines() if line.strip()]
    candidates = []
    for action in actions:
        if action.get("actor") != "A" or "hotkey('alt','f4')" not in (action.get("code") or ""):
            continue
        title = (action.get("window_before") or {}).get("output", "")
        if "inspection_note.txt" in title and "/outputs/agent_A" in title and "gedit" in title:
            candidates.append({"action_id": action["action_id"],
                               "window_before": title, "screenshot": action.get("screenshot")})
    result = {"delivered_note_opened_in_GUI": bool(candidates), "evidence": candidates}
    (run_root / "scripted_A_delivered_read.json").write_text(json.dumps(result, indent=2) + "\n")
    if not candidates:
        raise RuntimeError("Case 7 v1.0.2 scripted A did not open the delivered note in Text Editor")
    return result


def _control_case7_view_revisions(guest_a, guest_b, controllers, bridge, first,
                                  a_path: str, task_root: str, run_root: Path,
                                  run_id: str, spec) -> dict:
    """Additional GUI-only control for version history, never a model action."""
    from oscombo.collab.workspace_assembly_lite_v2 import scripted
    _launch(guest_a, "editor", a_path, run_id)
    changed = core._run_actor("A", guest_a, spec.AGENT_A_INSTRUCTION,
        scripted.a_probe_change(), run_root, max_steps=25, case_id=spec.CASE_ID)
    if changed["status"] != "done":
        raise RuntimeError("scripted A revision change failed")
    second = bridge.publish("A")
    original = (run_root / "fixtures" / spec.FIXTURE_NAMES["asset"]).read_text(encoding="utf-8")
    restored = core._run_actor("A", guest_a, spec.AGENT_A_INSTRUCTION,
        scripted.a_probe_restore(original), run_root, max_steps=25, case_id=spec.CASE_ID)
    if restored["status"] != "done":
        raise RuntimeError("scripted A revision restore failed")
    third = bridge.publish("A")
    revisions = [first, second, third]
    if not first["revision"] < second["revision"] < third["revision"]:
        raise RuntimeError("scripted probe did not create three distinct revisions")
    if not (first["sha256"] == third["sha256"] and second["sha256"] != first["sha256"]):
        raise RuntimeError("scripted probe did not restore the original note bytes")
    verified = []
    for revision in revisions:
        relative = revision.get("peer_view_path")
        if not relative:
            raise RuntimeError("scripted probe revision is missing its peer view")
        path = f"{task_root}/{relative}"
        data = controllers["B"].get_file(path)
        mode = _guest_script(guest_b, f"stat -c %a -- {shlex.quote(path)}")["output"].strip()
        if hashlib.sha256(data).hexdigest() != revision["sha256"] or mode != "444":
            raise RuntimeError("scripted probe peer view differs or is not read-only")
        saved = run_root / "control_views" / Path(relative).name
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_bytes(data)
        verified.append({"revision": revision["revision"], "peer_view_path": relative,
                         "sha256": revision["sha256"], "mode": mode,
                         "recovered_copy": str(saved.relative_to(run_root))})
    source_mode = _guest_script(guest_a, f"stat -c %a -- {shlex.quote(a_path)}")["output"].strip()
    if not source_mode.isdigit() or not (int(source_mode, 8) & 0o200):
        raise RuntimeError("A original output unexpectedly lost owner write permission")
    result = {"views": verified, "source_mode": source_mode,
              "change_trace": changed["trace_path"], "restore_trace": restored["trace_path"]}
    (run_root / "control_view_revisions.json").write_text(json.dumps(result, indent=2) + "\n")
    return third


def _browser_trace_audit(run_root: Path, *, write: bool = True) -> dict:
    """Count actual visible table rows in B's post-handoff Chrome screenshots.

    This is a conservative, pinned-Guest visual check. The final human trace
    audit also checks the typed query and selected status from screenshots.
    """
    from PIL import Image
    revision_time = None
    for line in (run_root / "workspace_versions/events.jsonl").read_text().splitlines():
        event = json.loads(line)
        if event.get("event") == "revision_saved" and event.get("actor") == "A" and event.get("revision", 0) >= 1:
            revision_time = event["time"]
            break
    candidates = []
    action_path = run_root / "gui_actions.jsonl"
    scripted = [json.loads(line) for line in action_path.read_text().splitlines()
                if line.strip()] if action_path.exists() else []
    model_path = run_root / "actor_runs/B/B/actions.jsonl"
    model_actions = [json.loads(line) for line in model_path.read_text().splitlines()
                     if line.strip()] if model_path.exists() else []
    observations = []
    for event in scripted:
        if event.get("actor") != "B":
            continue
        observations.append((event.get("ended_at", 0),
                             (event.get("window_after") or {}).get("output", ""),
                             event["action_id"], event["screenshot"]))
    for event in model_actions:
        if not event.get("executed") or event.get("tool") == "screenshot":
            continue
        observations.append((event.get("screenshot_ended_at", 0),
                             event.get("window_after") or "",
                             f"model-B-{event['n']:03d}",
                             f"actor_runs/B/B/shots/{event['n']:03d}.png"))
    for timestamp, title, action_id, shot_name in observations:
        if revision_time is None or timestamp < revision_time or "OrderDesk Lite" not in title:
            continue
        shot = run_root / shot_name
        if not shot.exists():
            continue
        with Image.open(shot) as image:
            gray = image.convert("L")
            width, height = gray.size
            if (width, height) not in {(1920, 1080), (1280, 720)}:
                continue
            sx, sy = width / 1920, height / 1080
            x_values = range(round(545 * sx), round(1446 * sx), max(1, round(3 * sx)))
            lines = []
            for y in range(round(350 * sy), round(650 * sy)):
                dark = sum(gray.getpixel((x, y)) < 220 for x in x_values)
                if dark >= int(0.8 * len(x_values)) and (not lines or y > lines[-1] + 1):
                    lines.append(y)
            rows = len(lines) - 2 if len(lines) >= 2 else None
        candidates.append({"action_id": action_id, "screenshot": shot_name,
                           "horizontal_borders": lines, "visible_rows": rows,
                           "after_A_revision": True})
    result = {"A_saved_revision_time": revision_time, "candidates": candidates,
              "browser_one_visible_row_after_handoff": any(x["visible_rows"] == 1 for x in candidates),
              "scope": "visible row count only; inspect query/status text and action chronology separately"}
    if write:
        (run_root / "browser_trace_audit.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def run(case: str, condition: str, run_root: Path, provider: Path, image: str, runtime: str,
        model: str | None, base_url: str, api_key_env: str, mcp_python: str,
        model_timeout: float, diagnostic_step_limit: int | None, negative: bool,
        yield_wait_lifecycle: bool = False,
        actor_mcp_only: bool = False,
        blender_bin: str | None = None,
        gui_input_lock: bool = False,
        scripted_view_version_probe: bool = False,
        fixture_seed: str | None = None) -> dict:
    spec, fixtures, oracle = _profile(case)
    if gui_input_lock and (not model or condition != "collaborative_shared"):
        raise ValueError("GUI input lock arm requires a Shared model run")
    if scripted_view_version_probe and (case != "workspace_assembly_v2" or model or negative):
        raise ValueError("view version probe requires a v2 scripted positive control")
    if fixture_seed is not None and case != "workspace_assembly_v2":
        raise ValueError("fixture seed is supported only for workspace assembly v2")
    if fixture_seed is not None:
        fixtures.tag_for_seed(fixture_seed)  # validate before allocating a run
    if case == "model_review" and (not blender_bin or not Path(blender_bin).is_file()):
        raise ValueError("Model-and-Review Lite needs a local Blender scorer executable")
    if condition not in spec.CONDITIONS:
        raise ValueError(condition)
    run_root.mkdir(parents=True, exist_ok=False)
    run_id = run_root.name
    fixture = run_root / "fixtures"
    if case == "workspace_assembly_v2":
        fixtures.build_fixture(fixture, seed=fixture_seed)
    else:
        fixtures.build_fixture(fixture)
    task_root = spec.TASK_ROOT if case == "workspace_assembly_v2" else f"/tmp/codesk-{case.replace('_', '-')}-lite-v1"
    metadata = {"run_id": run_id, "case_id": spec.CASE_ID, "case_version": spec.CASE_VERSION,
                "condition": condition, "guest_count": 1 if condition.endswith("shared") else 2,
                "model": model, "model_called": bool(model), "started_at": time.time(),
                "endpoint": base_url if model else None,
                "role_budget_contract": spec.ROLE_BUDGET,
                "yield_wait_lifecycle": bool(yield_wait_lifecycle),
                "actor_mcp_only": bool(actor_mcp_only),
                "gui_input_lock": bool(gui_input_lock),
                "gui_input_lock_scope": "one desktop input action; screenshot outside lock" if gui_input_lock else None,
                "blender_scorer": blender_bin if case == "model_review" else None,
                "scripted_negative_control": negative}
    if case == "workspace_assembly_v2":
        image_path = Path(image).resolve(strict=True)
        image_stat = image_path.stat()
        metadata["guest_resources_requested"] = {"cpus": os.environ.get("OSCOMBO_GUEST_CPUS", "4"),
                                                 "ram": os.environ.get("OSCOMBO_GUEST_RAM", "4G")}
        metadata["base_image_path"] = str(image_path)
        metadata["base_image_stat"] = {"bytes": image_stat.st_size, "mtime_ns": image_stat.st_mtime_ns}
        metadata["runtime_image"] = runtime
        metadata["scripted_view_version_probe"] = scripted_view_version_probe
        metadata["source_commit"] = os.environ.get("CODESK_CASE7_SOURCE_COMMIT")
        metadata["model_effort"] = "medium" if model else None
        metadata["model_timeout"] = model_timeout if model else None
        metadata["diagnostic_step_limit"] = diagnostic_step_limit
        metadata["fixture_seed"] = fixture_seed
    ledger = RunLedger(run_root, metadata)
    (run_root / "ownership.json").write_text(json.dumps({"run_id": run_id, "resources": [],
        "cleanup": "only exact owned oscombo.run label and full container ID"}, indent=2) + "\n")
    store = ProtocolStore(run_root / "collaboration", run_id)
    tokens = {role: secrets.token_urlsafe(32) for role in "AB"}
    server = make_server(store, tokens)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    clients = {r: CollaborationClient(f"http://127.0.0.1:{server.server_port}", r, tokens[r]) for r in "AB"}
    envs, guests, container_ids = {}, {}, {}
    resource_stop = threading.Event()
    resource_thread = threading.Thread(target=core._sample_guest_resources,
        args=(run_root, container_ids, resource_stop), daemon=True)
    resource_thread.start()
    bridge = None
    relay = None
    env_token_names = []
    reset_evidence = []
    cleanup_errors = []
    try:
        model_base = base_url
        if model:
            relay_env = "CODESK_RUN_RELAY_TOKEN"
            os.environ[relay_env] = secrets.token_urlsafe(32)
            env_token_names.append(relay_env)
            relay, model_base = core._start_codex_compat_relay(
                run_root, base_url, api_key_env, os.environ[relay_env], relay_env,
                actor_mcp_only=actor_mcp_only)
        for key in (("shared",) if condition.endswith("shared") else ("A", "B")):
            env, guest, cid = core._boot_guest(run_root, run_id, key, image, provider, runtime, ledger)
            envs[key], guests[key], container_ids[key] = env, guest, cid
            _install(guest, fixture, task_root, case, spec)
        guest_a = guests.get("shared") or guests["A"]
        guest_b = guests.get("shared") or guests["B"]
        controllers = {"A": guest_a.env.controller, "B": guest_b.env.controller}
        ids = {"A": guest_a.guest_key, "B": guest_b.guest_key}
        mime = ({"A": None, "B": None} if case == "build_verify" else
                {"A": "application/x-blender", "B": None} if case == "model_review" else
                {"A": None, "B": "application/vnd.oasis.opendocument.text"})
        bridge = SavedArtifactBridge(run_root / "workspace_versions", run_id, task_root,
                                     controllers, ids, case_id=spec.CASE_ID,
                                     outputs=spec.OUTPUTS, mime_types=mime,
                                     allow_initial_missing={"A"} if case in WORKSPACE_ASSEMBLY_CASES else None,
                                     peer_read_only=True,
                                     peer_view_dirs=spec.PEER_VIEW_DIRS if case == "workspace_assembly_v2" else None)
        server.workspace_bridge = bridge
        bridge.start()
        a_path = f"{task_root}/{spec.OUTPUTS['A']}"
        b_path = f"{task_root}/{spec.OUTPUTS['B']}"
        if case == "build_verify":
            _launch(guest_b, "editor", b_path, run_id)
            _launch(guest_a, "editor", a_path, run_id)
            _launch(guest_b, "browser", f"{task_root}/input/{spec.FIXTURE_NAMES['source']}", run_id)
            a_app, b_app = "editor", "editor"
        elif case == "model_review":
            if condition.endswith("isolated"):
                _launch(guest_b, "blender", a_path, run_id)
            _launch(guest_b, "editor", b_path, run_id)
            _launch(guest_a, "blender", a_path, run_id)
            a_app, b_app = "blender", "editor"
        else:
            _launch(guest_a, "files", f"{task_root}/incoming", run_id)
            if case in {"workspace_assembly_v1p2", "workspace_assembly_v2"}:
                _maximize_case7_files(guest_a)
            if case == "workspace_assembly_v2":
                guest_a.actor = "system"
                guest_a.run_pyautogui("import pyautogui, time; pyautogui.hotkey('ctrl','a'); time.sleep(2)")
                (run_root / "screenshots" / "setup_A_selected.png").write_bytes(guest_a.screenshot(patience=45))
            _launch(guest_b, "writer", b_path, run_id)
            if case == "workspace_assembly_v2":
                guest_b.actor = "system"
                guest_b.run_pyautogui("import pyautogui, time; pyautogui.hotkey('ctrl','end'); time.sleep(2)")
                (run_root / "screenshots" / "setup_B_caret.png").write_bytes(guest_b.screenshot(patience=45))
            a_app, b_app = "files", "writer"
        outcomes = {}
        if model:
            token_envs = core._model_collaboration_tokens(tokens, ("A", "B"))
            env_token_names.extend(token_envs.values())
            instructions = {
                "A": spec.AGENT_A_INSTRUCTION + f"\nTask root: {task_root}. Your output: {a_path}.",
                "B": spec.AGENT_B_INSTRUCTION + f"\nTask root: {task_root}. Your output: {b_path}.",
            }
            for role in "AB":
                if case == "workspace_assembly_v2":
                    instructions[role] = spec.model_instruction(role)
                else:
                    instructions[role] += ("\nSaved outputs are versioned and copied to the same paths on both desktops. "
                                          "After saving, use publish_saved_artifact and send_message; "
                                          "use list_saved_artifacts/read_messages for handoff. "
                                          "The peer file is read-only; do not edit it. "
                                          "Perform task edits only through GUI applications.")
            barrier = threading.Barrier(2)
            def actor(role):
                barrier.wait(timeout=60)
                guest = guest_a if role == "A" else guest_b
                actor_url = model_base.removesuffix("/v1") + f"/actor/{role}/v1"
                return core._run_model_actor(role, guest, instructions[role], run_root,
                    model, actor_url, api_key_env, mcp_python,
                    f"http://127.0.0.1:{server.server_port}", token_envs[role],
                    max_steps=core._effective_role_steps(role, diagnostic_step_limit, spec.ROLE_BUDGET),
                    timeout=model_timeout, relay_client_token_env=relay_env,
                    workspace_bridge=True, handoff_from=spec.HANDOFF_DEPENDENCIES.get(role),
                    yield_wait=yield_wait_lifecycle,
                    case_id=spec.CASE_ID,
                    gui_input_lock_path=str(run_root / "gui_input.lock") if gui_input_lock else None)
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="lite-file-actor") as pool:
                futures = {role: pool.submit(actor, role) for role in "AB"}
                for role, future in futures.items():
                    outcomes[role] = future.result()
        else:
            if case == "workspace_assembly_v2":
                from oscombo.collab.workspace_assembly.fixtures import read_odt
                from oscombo.collab.workspace_assembly_lite_v2 import scripted
                _activate(guest_b, "writer", b_path)
                audience_match = re.search(r"(?im)^Prepared for ([A-Za-z][A-Za-z -]+?) review\.$", fixtures.draft_text())
                if not audience_match:
                    raise RuntimeError("scripted control cannot derive the draft audience")
                pre = core._run_actor("B", guest_b, spec.AGENT_B_INSTRUCTION,
                    scripted.b_prepare(audience_match.group(1).title()), run_root, max_steps=25, case_id=spec.CASE_ID)
                if pre["status"] != "done":
                    raise RuntimeError("scripted B pre-handoff GUI failed")
                pre_path = run_root / "control_prework.odt"
                pre_path.write_bytes(controllers["B"].get_file(b_path))
                pre_text, _ = read_odt(pre_path)
                if ("Audience: " + audience_match.group(1).title() + ".") not in pre_text:
                    raise RuntimeError("scripted B pre-handoff edit was not saved")
                pre_revision = bridge.publish("B")
                (run_root / "control_prework.json").write_text(json.dumps({
                    "finished_at": time.time(), "sha256": hashlib.sha256(pre_path.read_bytes()).hexdigest(),
                    "revision": pre_revision["revision"], "trace_path": pre["trace_path"]}, indent=2) + "\n")
            if case == "build_verify":
                if condition.endswith("shared"):
                    _activate_editor_tab(guest_a, "A", True)
                else:
                    _activate(guest_a, "editor", a_path)
            elif case in WORKSPACE_ASSEMBLY_CASES:
                _activate(guest_a, "files", f"{task_root}/incoming")
            else:
                _activate(guest_a, "blender", a_path)
            outcomes["A"] = core._run_actor("A", guest_a, spec.AGENT_A_INSTRUCTION,
                _scripted_actions(case, "A", task_root, fixtures, negative), run_root,
                max_steps=25, case_id=spec.CASE_ID)
            if outcomes["A"]["status"] != "done":
                raise RuntimeError("scripted A GUI failed")
            if case == "workspace_assembly_v1p2":
                _audit_case7_scripted_delivered_read(run_root)
            if case in WORKSPACE_ASSEMBLY_CASES:
                probe = _guest_script(guest_a,
                    f"find {shlex.quote(task_root + '/incoming')} "
                    f"{shlex.quote(task_root + '/outputs/agent_A')} -maxdepth 1 -type f "
                    "-printf '%p %s bytes\\n'", timeout=20)
                (run_root / "file_move_probe.json").write_text(json.dumps(probe, indent=2) + "\n")
                _guest_script(guest_a, f"test ! -e {shlex.quote(task_root + '/incoming/' + spec.FIXTURE_NAMES['asset'])} "
                    f"&& test -s {shlex.quote(a_path)}")
            a_revision = bridge.publish("A")
            if scripted_view_version_probe:
                a_revision = _control_case7_view_revisions(guest_a, guest_b, controllers, bridge,
                    a_revision, a_path, task_root, run_root, run_id, spec)
            if controllers["B"].get_file(a_path) != controllers["A"].get_file(a_path):
                raise RuntimeError("B Guest did not receive A's saved version")
            message = (f"Saved {Path(a_path).name} revision {a_revision['revision']}; "
                       + ("filter defect fixed" if case == "build_verify" else
                          "shade width 1.46 m" if case == "model_review" else "inspection tag RIVER-27"))
            if case == "workspace_assembly_v2":
                message = f"Saved {Path(a_path).name} revision {a_revision['revision']} is ready."
            msg = clients["A"].send_message("B", message)
            if msg["message_id"] not in {m["message_id"] for m in clients["B"].read_messages()}:
                raise RuntimeError("B did not receive A's message")
            if case == "build_verify":
                _activate(guest_b, "browser", a_path)
            elif case == "model_review":
                # Scripted control observes the published scene in the real
                # Blender GUI; model B must choose its own reload/read action.
                if condition.endswith("isolated"):
                    _launch(guest_b, "blender", a_path, run_id)
                else:
                    _activate(guest_b, "blender", a_path)
                peer_shot = run_root / "screenshots" / "scripted-peer-blender-after-handoff.png"
                peer_shot.write_bytes(guest_b.screenshot(patience=45))
                (run_root / "scripted_peer_blender_read.json").write_text(json.dumps({
                    "published_A_revision": a_revision["revision"],
                    "guest_key": guest_b.guest_key,
                    "active_window": guest_b.active_window(),
                    "screenshot": str(peer_shot.relative_to(run_root)),
                    "saved_sha256": a_revision["sha256"]}, indent=2) + "\n")
                _activate(guest_b, "editor", b_path)
            elif case == "workspace_assembly_v2":
                view_relative = a_revision.get("peer_view_path")
                if not view_relative:
                    raise RuntimeError("published A revision has no peer view")
                view_path = f"{task_root}/{view_relative}"
                view_bytes = controllers["B"].get_file(view_path)
                if hashlib.sha256(view_bytes).hexdigest() != a_revision["sha256"]:
                    raise RuntimeError("B peer view SHA differs from published A revision")
                recovered_view = run_root / "control_views" / Path(view_relative).name
                recovered_view.parent.mkdir(parents=True, exist_ok=True)
                if recovered_view.exists() and recovered_view.read_bytes() != view_bytes:
                    raise RuntimeError("recovered peer view conflicts with prior control snapshot")
                if not recovered_view.exists():
                    recovered_view.write_bytes(view_bytes)
                mode = _guest_script(guest_b, f"stat -c %a -- {shlex.quote(view_path)}")["output"].strip()
                if mode != "444":
                    raise RuntimeError("B peer view is not read-only")
                owner_mode = _guest_script(guest_a, f"stat -c %a -- {shlex.quote(a_path)}")["output"].strip()
                if not owner_mode.isdigit() or not (int(owner_mode, 8) & 0o200):
                    raise RuntimeError("A original output unexpectedly lost owner write permission")
                _activate(guest_b, "writer", b_path)
                read = core._run_actor("B", guest_b, spec.AGENT_B_INSTRUCTION,
                    scripted.b_read(view_path), run_root, max_steps=25, case_id=spec.CASE_ID)
                if read["status"] != "done":
                    raise RuntimeError("scripted B peer-view GUI open failed")
                _case7_control_retry_open(guest_b, run_root, spec.AGENT_B_INSTRUCTION, spec.CASE_ID)
                title = ""
                for _ in range(12):
                    title = guest_b.active_window() or ""
                    if Path(view_path).name.casefold() in title.casefold() and "read-only" in title.casefold():
                        break
                    time.sleep(5)
                screenshot = run_root / "screenshots" / "control_B_peer_view.png"
                screenshot.write_bytes(guest_b.screenshot(patience=45))
                if Path(view_path).name.casefold() not in title.casefold() or "read-only" not in title.casefold():
                    raise RuntimeError("B did not visibly open the revision in read-only Writer")
                (run_root / "control_B_peer_view.json").write_text(json.dumps({
                    "revision": a_revision["revision"], "peer_view_path": view_relative,
                    "sha256": a_revision["sha256"], "mode": mode, "owner_mode": owner_mode,
                    "opened_at": time.time(), "window": title,
                    "recovered_copy": str(recovered_view.relative_to(run_root)),
                    "trace_path": read["trace_path"], "screenshot": str(screenshot.relative_to(run_root))}, indent=2) + "\n")
            else:
                # Smoke the real peer file in a GUI viewer before the scripted
                # Writer edit. Model actors must choose their own read action.
                _launch(guest_b, "editor", a_path, run_id)
                _activate(guest_b, "writer", b_path)
            b_actions = _scripted_actions(case, "B", task_root, fixtures, negative)
            if case == "workspace_assembly_v2":
                note = (fixture / spec.FIXTURE_NAMES["asset"]).read_text(encoding="utf-8")
                tag_match = re.search(r"(?m)^Inspection tag: ([A-Z][A-Z0-9]{2,9}-[0-9]{2})\.$", note)
                if not tag_match:
                    raise RuntimeError("scripted control cannot derive the public note tag")
                b_actions = scripted.b_finish("WRONG-00" if negative else tag_match.group(1))
            if case == "build_verify":
                browser_result = core._run_actor("B", guest_b, spec.AGENT_B_INSTRUCTION,
                    b_actions[:5] + ["DONE"], run_root, max_steps=25, case_id=spec.CASE_ID)
                if browser_result["status"] != "done":
                    raise RuntimeError("scripted browser QA failed")
                if condition.endswith("shared"):
                    _activate_editor_tab(guest_b, "B", True)
                else:
                    _activate(guest_b, "editor", b_path)
                b_actions = b_actions[5:]
            outcomes["B"] = core._run_actor("B", guest_b, spec.AGENT_B_INSTRUCTION,
                b_actions, run_root, max_steps=25, case_id=spec.CASE_ID)
            if outcomes["B"]["status"] != "done":
                raise RuntimeError("scripted B GUI failed")
            bridge.publish("B")
        bridge.stop()
        sync_result = {
            "final_versions": bridge.snapshot(), "transient_errors": bridge.errors,
            "verified": True}
        bridge_valid = True
        if case == "workspace_assembly_v2":
            diagnostics = bridge.diagnostics()
            bridge_valid = not diagnostics["infrastructure_review_required"]
            sync_result.update({"final_sync_succeeded": True,
                                "diagnostics": diagnostics, "verified": bridge_valid})
        (run_root / "workspace_sync_result.json").write_text(json.dumps(sync_result, indent=2) + "\n")
        bridge = None
        artifact_items = []
        missing_outputs = []
        for role, guest, path in (("A", guest_a, a_path), ("B", guest_b, b_path)):
            exists = _guest_script(guest,
                f"if test -s {shlex.quote(path)}; then printf 1; else printf 0; fi")["output"].strip() == "1"
            if exists:
                artifact_items.append({"actor": role, "guest_id": guest.guest_key,
                    "guest_path": path, "local_path": f"{role}/{Path(path).name}"})
            else:
                missing_outputs.append(role)
        (run_root / "missing_outputs.json").write_text(json.dumps(missing_outputs) + "\n")
        artifacts = collect_artifacts(run_root, artifact_items,
            core.GuestFiles({g.guest_key: g.env.controller for g in guests.values()}))
        if case == "build_verify":
            score = oracle.evaluate(fixture / spec.FIXTURE_NAMES["source"],
                run_root / "artifacts/A" / Path(a_path).name,
                fixture / spec.FIXTURE_NAMES["qa"],
                run_root / "artifacts/B" / Path(b_path).name)
        elif case == "model_review":
            score = oracle.evaluate(fixture / spec.FIXTURE_NAMES["scene"],
                run_root / "artifacts/A" / Path(a_path).name,
                fixture / spec.FIXTURE_NAMES["report"],
                run_root / "artifacts/B" / Path(b_path).name,
                blender_bin)
        else:
            incoming_guest = f"{task_root}/incoming/{spec.FIXTURE_NAMES['asset']}"
            incoming_present = _guest_script(guest_a,
                f"if test -e {shlex.quote(incoming_guest)}; then printf 1; else printf 0; fi")["output"].strip() == "1"
            incoming_local = run_root / "artifacts/A/incoming" / spec.FIXTURE_NAMES["asset"]
            if incoming_present:
                incoming_local.parent.mkdir(parents=True, exist_ok=True)
                incoming_local.write_bytes(controllers["A"].get_file(incoming_guest))
            score = oracle.evaluate(fixture / spec.FIXTURE_NAMES["asset"], incoming_local,
                run_root / "artifacts/A" / Path(a_path).name,
                fixture / spec.FIXTURE_NAMES["report"],
                run_root / "artifacts/B" / Path(b_path).name)
        (run_root / "oracle.json").write_text(json.dumps(score, indent=2, sort_keys=True) + "\n")
        oracle_fixture_valid = not (case == "workspace_assembly_v2" and
                                    (score.get("invalid_fixture") or score.get("invalid_scorer")))
        browser_trace = _browser_trace_audit(run_root) if case == "build_verify" else None
        process_audit = None
        if case == "workspace_assembly_v2" and model:
            from oscombo.collab.workspace_assembly_lite_v2.audit import audit
            process_audit = audit(run_root)
            (run_root / "behavioral_audit.json").write_text(json.dumps(process_audit, indent=2) + "\n")
        reopen = []
        for role, guest, app, path in (("A", guest_a, a_app, a_path), ("B", guest_b, b_app, b_path)):
            if role in missing_outputs:
                reopen.append({"role": role, "guest": guest.guest_key,
                               "same_bytes": False, "missing_output": True})
                continue
            data_before = guest.env.controller.get_file(path)
            try:
                if app != "files":
                    if case == "build_verify" and condition.endswith("shared"):
                        _activate_editor_tab(guest, role, True)
                    elif case == "workspace_assembly_v2" and app == "writer" and model:
                        restored_closed_writer = _restore_closed_case7_writer(guest, path, run_id)
                    else:
                        _activate(guest, app, path)
                    # A dirty Text Editor tab may not be safely closed from
                    # the generic GUI path. Preserve the already scored bytes
                    # and record that GUI reopen was not verified.
                    active_title = guest.active_window() or ""
                    if app == "editor" and _editor_has_unsaved_buffer(active_title, path):
                        reopen.append({"role": role, "guest": guest.guest_key,
                                       "same_bytes": True, "gui_reopen": "skipped_unsaved_buffer",
                                       "saved_sha256": hashlib.sha256(data_before).hexdigest()})
                        continue
                    if case == "workspace_assembly_v2" and app == "writer" and model and restored_closed_writer:
                        discarded_unsaved = False
                    else:
                        guest.actor = "system"
                        guest.run_pyautogui("import pyautogui, time; pyautogui.hotkey('alt','f4'); time.sleep(2)"
                                            if app == "blender" else
                                            "import pyautogui, time; pyautogui.hotkey('ctrl','w'); time.sleep(2)")
                        discarded_unsaved = core._discard_postscore_unsaved_dialog(
                            guest, f"reopen-{role}-close")
                        _launch(guest, app, path, run_id)
                else:
                    discarded_unsaved = False
                    _launch(guest, "files", f"{task_root}/outputs/agent_A", run_id)
                data_after = guest.env.controller.get_file(path)
                if data_before != data_after:
                    raise RuntimeError(f"{role} saved bytes changed during GUI reopen")
                reopen.append({"role": role, "guest": guest.guest_key,
                    "sha256": hashlib.sha256(data_after).hexdigest(), "same_bytes": True,
                    "discarded_uncommitted_buffer_after_scoring": discarded_unsaved})
            except (RuntimeError, TimeoutError) as exc:
                # Oracle already scored the saved bytes. Keep its judgement
                # separate from a blocked postscore GUI lifecycle and reset
                # only this run's Guest in the normal path below.
                shot_path = run_root / "screenshots" / f"reopen-{role}-failed.png"
                try:
                    shot_path.write_bytes(guest.screenshot(patience=45))
                    shot = str(shot_path.relative_to(run_root))
                except Exception:
                    shot = None
                reopen.append({"role": role, "guest": guest.guest_key,
                    "same_bytes": False, "saved_sha256": hashlib.sha256(data_before).hexdigest(),
                    "postscore_error": f"{type(exc).__name__}: {exc}", "screenshot": shot})
        (run_root / "reopen_evidence.json").write_text(json.dumps(reopen, indent=2) + "\n")
        reopen_complete = (len(reopen) == 2 and all(item.get("same_bytes") is True
                            and item.get("gui_reopen") != "skipped_unsaved_buffer" for item in reopen))
        # A missing Actor output is a task failure, not a GUI reopen fault.
        # A failed reopen of an existing saved output is infrastructure-invalid
        # even when the already-scored Oracle also rejected the task.
        postscore_lifecycle_ok = _postscore_lifecycle_ok(reopen)
        for key, env in envs.items():
            old_id = container_ids[key]
            core._verify_container(old_id, run_id)
            os.environ["OSCOMBO_OVERLAY_DIR"] = str(run_root / "overlay" / key)
            os.environ["SWCUB_VM_OVERLAY"] = str(run_root / "overlay" / key)
            os.environ["OSCOMBO_RUN_LABEL"] = run_id
            env.is_environment_used = True
            env.reset()
            new_container, labels = core._owned_container(env, run_id)
            if new_container.id == old_id or not core._missing_container(old_id):
                raise RuntimeError("reset did not replace run-owned Guest")
            _guest_script(guests[key], f"test ! -e {shlex.quote(task_root)} && ! pgrep -x soffice.bin >/dev/null")
            container_ids[key] = new_container.id
            reset_evidence.append({"guest": key, "old": old_id, "new": new_container.id,
                                   "workspace_clean": True, "labels": labels})
        (run_root / "reset_evidence.json").write_text(json.dumps(reset_evidence, indent=2) + "\n")
        result = {"run_id": run_id, "case_id": spec.CASE_ID, "condition": condition,
                  "model": model, "actor_results": outcomes, "oracle": score,
                  "browser_trace_audit": browser_trace,
                  "artifact_manifest": artifacts, "reopen": reopen,
                  "reopen_complete": reopen_complete,
                  "postscore_lifecycle_ok": postscore_lifecycle_ok,
                  "reset": reset_evidence, "elapsed_s": time.time() - metadata["started_at"],
                  "status": core._episode_result_status(score["joint_success"] and
                      (browser_trace is None or browser_trace["browser_one_visible_row_after_handoff"]),
                      postscore_lifecycle_ok and bridge_valid and oracle_fixture_valid, outcomes, bool(model))}
        if case == "workspace_assembly_v2":
            result.update({"behavioral_audit": process_audit, "bridge_valid": bridge_valid,
                           "oracle_fixture_valid": oracle_fixture_valid})
        (run_root / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result
    finally:
        resource_stop.set()
        resource_thread.join(timeout=10)
        defer_guests = _stop_bridge_before_cleanup(
            bridge, case, run_root, run_id, container_ids, cleanup_errors)
        for name in env_token_names:
            os.environ.pop(name, None)
        for key, env in (() if defer_guests else envs.items()):
            cid = container_ids[key]
            try:
                core._verify_container(cid, run_id)
                env.close()
                if not core._missing_container(cid):
                    raise RuntimeError(f"owned Guest {cid} remains after close")
                core._append(run_root / "resource_actions.jsonl", {"event": "guest_closed",
                    "guest": key, "full_container_id": cid, "run_id": run_id})
            except Exception as exc:
                cleanup_errors.append(f"{key}: {type(exc).__name__}: {exc}")
                core._append(run_root / "cleanup_errors.jsonl", {"guest": key, "error": str(exc)})
        if relay is not None:
            relay.terminate()
            try:
                relay.wait(timeout=10)
            except subprocess.TimeoutExpired:
                relay.kill()
                relay.wait(timeout=5)
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)
        if cleanup_errors:
            result_path = run_root / "result.json"
            if result_path.exists():
                existing = json.loads(result_path.read_text())
                existing["pre_cleanup_status"] = existing.get("status")
                existing["status"] = "INVALID_INFRA_OR_RUNNER_ERROR"
                existing["cleanup_errors"] = cleanup_errors
                tmp = result_path.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n")
                tmp.replace(result_path)
            raise RuntimeError("run-owned Guest cleanup incomplete: " + "; ".join(cleanup_errors))


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=("build_verify", "workspace_assembly", "workspace_assembly_v1p2", "workspace_assembly_v2", "model_review"))
    parser.add_argument("--condition", required=True,
                        choices=("collaborative_shared", "collaborative_isolated"))
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--provider", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--model")
    parser.add_argument("--base-url", default="https://api.openai.com/v1")
    parser.add_argument("--api-key-env", default="AIGCBEST_API_KEY")
    parser.add_argument("--mcp-python", default=sys.executable)
    parser.add_argument("--model-timeout", type=float, default=1200)
    parser.add_argument("--diagnostic-step-limit", type=int)
    parser.add_argument("--scripted-negative", action="store_true")
    parser.add_argument("--scripted-view-version-probe", action="store_true",
                        help="v2 scripted positive: save, change and restore a peer view to test revision history")
    parser.add_argument("--fixture-seed", help="v2 deterministic public note seed; identical within a paired round")
    parser.add_argument("--yield-wait-lifecycle", action="store_true",
                        help="pause B's active model budget after it voluntarily yields for A's handoff")
    parser.add_argument("--actor-mcp-only", action="store_true",
                        help="model sees only the desktop and collaboration MCP tools")
    parser.add_argument("--gui-input-lock", action="store_true",
                        help="Shared model ablation: serialize GUI input calls only, leave screenshots unlocked")
    parser.add_argument("--blender-bin", help="host-side Blender scorer for model_review")
    args = parser.parse_args(argv)
    run_root = args.run_root.resolve()
    if args.model and not os.environ.get(args.api_key_env):
        parser.error(f"model requested but {args.api_key_env} is unset")
    try:
        result = run(args.case, args.condition, run_root,
                     args.provider.resolve(), args.image, args.runtime,
                     args.model, args.base_url, args.api_key_env, args.mcp_python,
                     args.model_timeout, args.diagnostic_step_limit, args.scripted_negative,
                     args.yield_wait_lifecycle, args.actor_mcp_only, args.blender_bin,
                     args.gui_input_lock, args.scripted_view_version_probe, args.fixture_seed)
    except Exception as exc:
        failure = {"status": "INVALID_INFRA_OR_RUNNER_ERROR", "run_id": args.run_root.name,
                   "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}
        if run_root.exists():
            (run_root / "failure.json").write_text(json.dumps(failure, indent=2) + "\n")
        print(json.dumps(failure, indent=2), file=sys.stderr)
        raise SystemExit(3)
    print(json.dumps(result, indent=2))
    raise SystemExit(_result_exit_code(result["status"]))


if __name__ == "__main__":
    main()
