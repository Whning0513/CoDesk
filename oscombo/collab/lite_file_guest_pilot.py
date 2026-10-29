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


def _profile(case: str):
    if case == "build_verify":
        from oscombo.collab.build_and_verify_lite_v1 import spec, fixtures, oracle
    elif case == "workspace_assembly":
        from oscombo.collab.workspace_assembly_lite_v1 import spec, fixtures, oracle
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
    else:
        commands.append(f"cp {shlex.quote(task_root + '/input/' + names['asset'])} "
                        f"{shlex.quote(task_root + '/incoming/' + names['asset'])}")
        commands.append(f"chmod u+w {shlex.quote(task_root + '/incoming/' + names['asset'])}")
        commands.append(f"cp {shlex.quote(task_root + '/input/' + names['report'])} "
                        f"{shlex.quote(task_root + '/' + spec.OUTPUTS['B'])}")
        commands.append(f"chmod u+w {shlex.quote(task_root + '/' + spec.OUTPUTS['B'])}")
    _guest_script(guest, "set -e\n" + "\n".join(commands), timeout=60)


def _launch(guest, app: str, path: str, run_id: str):
    """Setup/reopen only. Never used to arbitrate model-time GUI focus."""
    if app == "writer":
        return core._launch(guest, "writer", path, f"/tmp/{run_id}/writer.log")
    choices = {
        "editor": "command -v gedit || command -v gnome-text-editor || command -v mousepad",
        "browser": "command -v google-chrome || command -v chromium-browser || command -v chromium",
        "files": "command -v nautilus || command -v thunar",
    }
    if app not in choices:
        raise ValueError(app)
    quoted = shlex.quote(path)
    check = _guest_script(guest, choices[app], timeout=15)
    binary = (check.get("output") or "").strip().splitlines()[-1]
    if not binary.startswith("/"):
        raise RuntimeError(f"Guest {app} application not found")
    args = "--no-first-run --no-default-browser-check " if app == "browser" else ""
    uri = "file://" + path if app == "browser" else path
    _guest_script(guest, f"mkdir -p /tmp/{shlex.quote(run_id)}; "
                  f"nohup {shlex.quote(binary)} {args}{shlex.quote(uri)} "
                  f">/tmp/{shlex.quote(run_id)}/{app}.log 2>&1 </dev/null &", timeout=15)
    deadline = time.monotonic() + 120
    hint = "OrderDesk Lite" if app == "browser" else Path(path).name
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


def _activate(guest, app: str, path: str):
    if app == "writer":
        return core._activate_ready_document(guest, path, "lite-file-reopen")
    hint = "OrderDesk Lite" if app == "browser" else Path(path).name
    _guest_script(guest, f"wmctrl -a {shlex.quote(hint)}", timeout=15)
    if hint.casefold() not in (guest.active_window() or "").casefold():
        raise RuntimeError(f"cannot activate {hint}")


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
            "import pyautogui, time; pyautogui.hotkey('ctrl','shift','r'); time.sleep(3)",
            "import pyautogui, time; pyautogui.click(680,268); pyautogui.write('North', 0.1); time.sleep(1)",
            "import pyautogui, time; pyautogui.click(1050,268); pyautogui.press('end'); pyautogui.press('enter'); time.sleep(1)",
            "import pyautogui, time; pyautogui.click(1180,268); time.sleep(3)",
            "import pyautogui, time; pyautogui.hotkey('ctrl','a'); time.sleep(1)",
            f"import pyautogui, time; pyautogui.write({note!r}, 0.03); time.sleep(1)",
            "import pyautogui, time; pyautogui.hotkey('ctrl','s'); time.sleep(3)", "DONE"]
    if case == "workspace_assembly" and role == "A":
        return [
            "import pyautogui, time; pyautogui.hotkey('ctrl','a'); time.sleep(2)",
            "import pyautogui, time; pyautogui.hotkey('ctrl','x'); time.sleep(2)",
            f"import pyautogui, time; pyautogui.hotkey('ctrl','l'); pyautogui.write({(task_root + '/outputs/agent_A')!r}, 0.01); pyautogui.press('enter'); time.sleep(2)",
            "import pyautogui, time; pyautogui.hotkey('ctrl','v'); time.sleep(3)", "DONE"]
    if case == "workspace_assembly" and role == "B":
        sentence = ("The delivered inspection attachment is inspection_note.txt with inspection tag " +
                    ("WRONG." if negative else "RIVER-27."))
        text = "Aurora Supply Handoff\n" + sentence + "\nPrepared for operations review."
        return ["import pyautogui, time; pyautogui.hotkey('ctrl','a'); time.sleep(1)",
                f"import pyautogui, time; pyautogui.write({text!r}, 0.03); time.sleep(2)",
                "import pyautogui, time; pyautogui.hotkey('ctrl','s'); time.sleep(3)", "DONE"]
    raise ValueError((case, role))


def _browser_trace_audit(run_root: Path) -> dict:
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
    for line in action_path.read_text().splitlines() if action_path.exists() else ():
        event = json.loads(line)
        if event.get("actor") != "B" or revision_time is None or event.get("ended_at", 0) < revision_time:
            continue
        title = (event.get("window_after") or {}).get("output", "")
        if "OrderDesk Lite" not in title:
            continue
        shot = run_root / event["screenshot"]
        with Image.open(shot) as image:
            gray = image.convert("L")
            if gray.size != (1920, 1080):
                continue
            lines = []
            for y in range(350, 650):
                dark = sum(gray.getpixel((x, y)) < 180 for x in range(545, 1446, 3))
                if dark >= 250 and (not lines or y > lines[-1] + 1):
                    lines.append(y)
            rows = len(lines) - 2 if len(lines) >= 2 else None
        candidates.append({"action_id": event["action_id"], "screenshot": event["screenshot"],
                           "horizontal_borders": lines, "visible_rows": rows,
                           "after_A_revision": True})
    result = {"A_saved_revision_time": revision_time, "candidates": candidates,
              "browser_one_visible_row_after_handoff": any(x["visible_rows"] == 1 for x in candidates),
              "scope": "visible row count only; inspect query/status text and action chronology separately"}
    (run_root / "browser_trace_audit.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def run(case: str, condition: str, run_root: Path, provider: Path, image: str, runtime: str,
        model: str | None, base_url: str, api_key_env: str, mcp_python: str,
        model_timeout: float, diagnostic_step_limit: int | None, negative: bool) -> dict:
    spec, fixtures, oracle = _profile(case)
    if condition not in spec.CONDITIONS:
        raise ValueError(condition)
    run_root.mkdir(parents=True, exist_ok=False)
    run_id = run_root.name
    fixture = run_root / "fixtures"
    fixtures.build_fixture(fixture)
    task_root = f"/tmp/codesk-{case.replace('_', '-')}-lite-v1"
    metadata = {"run_id": run_id, "case_id": spec.CASE_ID, "case_version": spec.CASE_VERSION,
                "condition": condition, "guest_count": 1 if condition.endswith("shared") else 2,
                "model": model, "model_called": bool(model), "started_at": time.time(),
                "endpoint": base_url if model else None,
                "role_budget_contract": spec.ROLE_BUDGET,
                "scripted_negative_control": negative}
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
                run_root, base_url, api_key_env, os.environ[relay_env], relay_env)
        for key in (("shared",) if condition.endswith("shared") else ("A", "B")):
            env, guest, cid = core._boot_guest(run_root, run_id, key, image, provider, runtime, ledger)
            envs[key], guests[key], container_ids[key] = env, guest, cid
            _install(guest, fixture, task_root, case, spec)
        guest_a = guests.get("shared") or guests["A"]
        guest_b = guests.get("shared") or guests["B"]
        controllers = {"A": guest_a.env.controller, "B": guest_b.env.controller}
        ids = {"A": guest_a.guest_key, "B": guest_b.guest_key}
        mime = ({"A": None, "B": None} if case == "build_verify" else
                {"A": None, "B": "application/vnd.oasis.opendocument.text"})
        bridge = SavedArtifactBridge(run_root / "workspace_versions", run_id, task_root,
                                     controllers, ids, case_id=spec.CASE_ID,
                                     outputs=spec.OUTPUTS, mime_types=mime,
                                     allow_initial_missing={"A"} if case == "workspace_assembly" else None,
                                     peer_read_only=True)
        server.workspace_bridge = bridge
        bridge.start()
        a_path = f"{task_root}/{spec.OUTPUTS['A']}"
        b_path = f"{task_root}/{spec.OUTPUTS['B']}"
        if case == "build_verify":
            _launch(guest_b, "editor", b_path, run_id)
            _launch(guest_a, "editor", a_path, run_id)
            _launch(guest_b, "browser", a_path, run_id)
            a_app, b_app = "editor", "editor"
        else:
            _launch(guest_a, "files", f"{task_root}/incoming", run_id)
            _launch(guest_b, "writer", b_path, run_id)
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
                    case_id=spec.CASE_ID)
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="lite-file-actor") as pool:
                futures = {role: pool.submit(actor, role) for role in "AB"}
                for role, future in futures.items():
                    outcomes[role] = future.result()
        else:
            if case == "build_verify":
                if condition.endswith("shared"):
                    _activate_editor_tab(guest_a, "A", True)
                else:
                    _activate(guest_a, "editor", a_path)
            else:
                _activate(guest_a, "files", f"{task_root}/incoming")
            outcomes["A"] = core._run_actor("A", guest_a, spec.AGENT_A_INSTRUCTION,
                _scripted_actions(case, "A", task_root, fixtures, negative), run_root,
                max_steps=25, case_id=spec.CASE_ID)
            if outcomes["A"]["status"] != "done":
                raise RuntimeError("scripted A GUI failed")
            if case == "workspace_assembly":
                probe = _guest_script(guest_a,
                    f"find {shlex.quote(task_root + '/incoming')} "
                    f"{shlex.quote(task_root + '/outputs/agent_A')} -maxdepth 1 -type f "
                    "-printf '%p %s bytes\\n'", timeout=20)
                (run_root / "file_move_probe.json").write_text(json.dumps(probe, indent=2) + "\n")
                _guest_script(guest_a, f"test ! -e {shlex.quote(task_root + '/incoming/' + spec.FIXTURE_NAMES['asset'])} "
                    f"&& test -s {shlex.quote(a_path)}")
            a_revision = bridge.publish("A")
            if controllers["B"].get_file(a_path) != controllers["A"].get_file(a_path):
                raise RuntimeError("B Guest did not receive A's saved version")
            msg = clients["A"].send_message("B", f"Saved {Path(a_path).name} revision {a_revision['revision']}; "
                    + ("filter defect fixed" if case == "build_verify" else "inspection tag RIVER-27"))
            if msg["message_id"] not in {m["message_id"] for m in clients["B"].read_messages()}:
                raise RuntimeError("B did not receive A's message")
            if case == "build_verify":
                _activate(guest_b, "browser", a_path)
            else:
                # Smoke the real peer file in a GUI viewer before the scripted
                # Writer edit. Model actors must choose their own read action.
                _launch(guest_b, "editor", a_path, run_id)
                _activate(guest_b, "writer", b_path)
            b_actions = _scripted_actions(case, "B", task_root, fixtures, negative)
            if case == "build_verify":
                browser_result = core._run_actor("B", guest_b, spec.AGENT_B_INSTRUCTION,
                    b_actions[:4] + ["DONE"], run_root, max_steps=25, case_id=spec.CASE_ID)
                if browser_result["status"] != "done":
                    raise RuntimeError("scripted browser QA failed")
                if condition.endswith("shared"):
                    _activate_editor_tab(guest_b, "B", True)
                else:
                    _activate(guest_b, "editor", b_path)
                b_actions = b_actions[4:]
            outcomes["B"] = core._run_actor("B", guest_b, spec.AGENT_B_INSTRUCTION,
                b_actions, run_root, max_steps=25, case_id=spec.CASE_ID)
            if outcomes["B"]["status"] != "done":
                raise RuntimeError("scripted B GUI failed")
            bridge.publish("B")
        bridge.stop()
        (run_root / "workspace_sync_result.json").write_text(json.dumps({
            "final_versions": bridge.snapshot(), "transient_errors": bridge.errors,
            "verified": True}, indent=2) + "\n")
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
        browser_trace = _browser_trace_audit(run_root) if case == "build_verify" else None
        reopen = []
        for role, guest, app, path in (("A", guest_a, a_app, a_path), ("B", guest_b, b_app, b_path)):
            if role in missing_outputs:
                reopen.append({"role": role, "guest": guest.guest_key,
                               "same_bytes": False, "missing_output": True})
                continue
            data_before = guest.env.controller.get_file(path)
            if app != "files":
                if case == "build_verify" and condition.endswith("shared"):
                    _activate_editor_tab(guest, role, True)
                else:
                    _activate(guest, app, path)
                guest.actor = "system"
                guest.run_pyautogui("import pyautogui, time; pyautogui.hotkey('ctrl','w'); time.sleep(2)")
                _launch(guest, app, path, run_id)
            else:
                _launch(guest, "files", f"{task_root}/outputs/agent_A", run_id)
            data_after = guest.env.controller.get_file(path)
            if data_before != data_after:
                raise RuntimeError(f"{role} saved bytes changed during GUI reopen")
            reopen.append({"role": role, "guest": guest.guest_key,
                "sha256": hashlib.sha256(data_after).hexdigest(), "same_bytes": True})
        (run_root / "reopen_evidence.json").write_text(json.dumps(reopen, indent=2) + "\n")
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
                  "reset": reset_evidence, "elapsed_s": time.time() - metadata["started_at"],
                  "status": core._episode_result_status(score["joint_success"] and
                      (browser_trace is None or browser_trace["browser_one_visible_row_after_handoff"]),
                      not missing_outputs, outcomes, bool(model))}
        (run_root / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result
    finally:
        resource_stop.set()
        resource_thread.join(timeout=10)
        if bridge is not None:
            try:
                bridge.stop()
            except Exception as exc:
                core._append(run_root / "workspace_sync_errors.jsonl", {"error": str(exc), "time": time.time()})
        for name in env_token_names:
            os.environ.pop(name, None)
        for key, env in envs.items():
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
            raise RuntimeError("run-owned Guest cleanup incomplete: " + "; ".join(cleanup_errors))


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=("build_verify", "workspace_assembly"))
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
    args = parser.parse_args(argv)
    run_root = args.run_root.resolve()
    if args.model and not os.environ.get(args.api_key_env):
        parser.error(f"model requested but {args.api_key_env} is unset")
    try:
        result = run(args.case, args.condition, run_root,
                     args.provider.resolve(), args.image, args.runtime,
                     args.model, args.base_url, args.api_key_env, args.mcp_python,
                     args.model_timeout, args.diagnostic_step_limit, args.scripted_negative)
    except Exception as exc:
        failure = {"status": "INVALID_INFRA_OR_RUNNER_ERROR", "run_id": args.run_root.name,
                   "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}
        if run_root.exists():
            (run_root / "failure.json").write_text(json.dumps(failure, indent=2) + "\n")
        print(json.dumps(failure, indent=2), file=sys.stderr)
        raise SystemExit(3)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 2)


if __name__ == "__main__":
    main()
