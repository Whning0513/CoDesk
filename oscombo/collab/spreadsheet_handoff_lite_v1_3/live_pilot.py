"""Scripted real-Guest adapter for Spreadsheet Handoff Lite v1.3.

This entry point deliberately has no model/API option. Importing the module is
offline; invoking ``main`` starts OSWorld Guest(s). It reuses the established
Lite file pilot's Guest helpers and SavedArtifactBridge without changing that
shared pilot or any earlier Case 6 version. This adapter has only offline
unit coverage so far and must not be described as Guest-validated.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
import threading
import time
import traceback
from pathlib import Path

from oscombo.collab import lite_file_guest_pilot as shared_pilot
from oscombo.collab.data_to_deck.collab_tools import CollaborationClient
from oscombo.collab.data_to_deck.protocol import ProtocolStore, make_server
from oscombo.collab.data_to_deck.provenance import RunLedger, collect_artifacts
from oscombo.collab.data_to_deck.workspace_bridge import SavedArtifactBridge

from . import adapter

core = shared_pilot.core


def _save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def _install_v13(guest, fixture: Path, case_version: str) -> None:
    """Install the selected public v1.3 fixture through the shared Guest helper."""
    spec, _, _ = adapter.select_case(case_version)
    core._install_fixture(guest, fixture, spec.TASK_ROOT, spec,
                          source_keys=("forecast", "order"))
    shared_pilot._guest_script(guest,
        f"mkdir -p {spec.TASK_ROOT}/incoming/A {spec.TASK_ROOT}/incoming/B", timeout=15)


def _launch_calc(guest, path: str, run_id: str) -> None:
    core._launch(guest, "calc", path, f"/tmp/{run_id}/calc.log")


def _activate_calc(guest, path: str) -> None:
    title = Path(path).name
    shared_pilot._guest_script(guest, f"wmctrl -a {shlex.quote(title)}", timeout=15)
    active = guest.active_window() or ""
    if title.casefold() not in active.casefold():
        raise RuntimeError(f"could not activate Calc workbook {title!r}; active={active!r}")


def _trace_actions(run_root: Path, actor_summary: dict) -> list[dict]:
    path = run_root / actor_summary["trace_path"]
    trace = json.loads(path.read_text(encoding="utf-8"))
    return [action for step in trace for action in step.get("actions", [])]


def _guest_controls(case_version: str, condition: str, run_root: Path,
                    provider: Path, image: str, runtime: str,
                    negative: bool = False) -> dict:
    spec, fixtures, oracle = adapter.select_case(case_version)
    if condition not in spec.CONDITIONS:
        raise ValueError(f"unsupported condition for v{case_version}: {condition}")
    run_id = run_root.name
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{5,95}", run_id):
        raise ValueError("run-root basename must be a unique safe run_id (6-96 characters)")
    run_root = run_root.resolve()
    original_cwd = Path.cwd()
    original_sys_path = list(sys.path)
    managed_env = ("OSWORLD_DIR", "OSCOMBO_GUEST_IMAGE", "OSCOMBO_RUNTIME_IMAGE",
                   "OSCOMBO_OVERLAY_DIR", "SWCUB_VM_OVERLAY", "OSCOMBO_RUN_LABEL",
                   "OSCOMBO_GUEST_RAM", "OSCOMBO_GUEST_CPUS", "OSCOMBO_VM_READY_TIMEOUT")
    original_env = {name: os.environ.get(name) for name in managed_env}
    run_root.mkdir(parents=True, exist_ok=False)
    fixture = run_root / "fixtures"
    fixtures.build_fixture(fixture)
    shared = condition.endswith("shared")
    metadata = {
        "run_id": run_id, "case_id": spec.CASE_ID, "case_version": spec.CASE_VERSION,
        "condition": condition, "guest_count": 1 if shared else 2,
        "model": None, "model_called": False, "adapter": "scripted-v1.3",
        "control": "negative" if negative else "positive",
        "started_at": time.time(), "task_root": spec.TASK_ROOT,
        "role_budget_contract": spec.ROLE_BUDGET,
        "guest_validation_status": "not_run_by_offline_checks",
    }
    ledger = RunLedger(run_root, metadata)
    _save_json(run_root / "ownership.json", {"run_id": run_id, "resources": [],
        "cleanup": "only exact owned oscombo.run label and full container ID"})
    store = ProtocolStore(run_root / "collaboration", run_id)
    import secrets
    tokens = {role: secrets.token_urlsafe(32) for role in "AB"}
    server = make_server(store, tokens)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    clients = {role: CollaborationClient(f"http://127.0.0.1:{server.server_port}", role, tokens[role])
               for role in "AB"}
    envs, guests, container_ids = {}, {}, {}
    resource_stop = threading.Event()
    resource_thread = threading.Thread(target=core._sample_guest_resources,
        args=(run_root, container_ids, resource_stop), daemon=True)
    resource_thread.start()
    bridge = None
    reset_evidence = []
    cleanup_errors = []
    try:
        for key in (("shared",) if shared else ("A", "B")):
            env, guest, cid = core._boot_guest(run_root, run_id, key, image, provider, runtime, ledger)
            envs[key], guests[key], container_ids[key] = env, guest, cid
            _install_v13(guest, fixture, case_version)

        guest_a = guests.get("shared") or guests["A"]
        guest_b = guests.get("shared") or guests["B"]
        controllers = {"A": guest_a.env.controller, "B": guest_b.env.controller}
        guest_ids = {"A": guest_a.guest_key, "B": guest_b.guest_key}
        bridge = SavedArtifactBridge(
            run_root / "workspace_versions", run_id, spec.TASK_ROOT, controllers, guest_ids,
            case_id=spec.CASE_ID, outputs=spec.OUTPUTS,
            mime_types={"A": "application/vnd.oasis.opendocument.spreadsheet",
                        "B": "application/vnd.oasis.opendocument.spreadsheet"},
            peer_read_only=True, peer_view_dirs={"A": "incoming/A", "B": "incoming/B"})
        server.workspace_bridge = bridge
        bridge.start()
        a_path = f"{spec.TASK_ROOT}/{spec.OUTPUTS['A']}"
        b_path = f"{spec.TASK_ROOT}/{spec.OUTPUTS['B']}"
        if shared:
            # Both files are open in the same Calc desktop. The final launch
            # selects A's initial workbook; actors retain normal GUI control.
            _launch_calc(guest_a, b_path, run_id)
            _launch_calc(guest_a, a_path, run_id)
        else:
            _launch_calc(guest_a, a_path, run_id)
            _launch_calc(guest_b, b_path, run_id)

        scripted = adapter.scripted_actions(negative)
        _activate_calc(guest_a, a_path)
        a_result = core._run_actor("A", guest_a, spec.AGENT_A_INSTRUCTION,
            scripted["A"], run_root, max_steps=10, case_id=spec.CASE_ID)
        if a_result.get("status") != "done":
            raise RuntimeError(f"scripted A GUI control ended as {a_result.get('status')}")
        a_revision = bridge.publish("A")
        published_at = time.time()
        if not a_revision.get("peer_view_path"):
            raise RuntimeError("bridge did not return A's immutable peer-view path")
        peer_path = f"{spec.TASK_ROOT}/{a_revision['peer_view_path']}"
        peer_payload = controllers["B"].get_file(peer_path)
        peer_sha = adapter.sha256_bytes(peer_payload or b"") if peer_payload else None
        message = clients["A"].send_message("B", "The saved forecast revision is ready for procurement review.")
        received = clients["B"].read_messages()
        received_ids = {item["message_id"] for item in received}
        message_received_at = time.time()
        if message["message_id"] not in received_ids:
            raise RuntimeError("B did not receive A's ready message")

        _activate_calc(guest_b, b_path)
        b_read_result = core._run_actor("B", guest_b, spec.AGENT_B_INSTRUCTION,
            adapter.peer_read_actions(peer_path), run_root, max_steps=8, case_id=spec.CASE_ID)
        if b_read_result.get("status") != "done":
            raise RuntimeError(f"scripted B GUI peer-read ended as {b_read_result.get('status')}")
        gui_read_at = time.time()
        peer_shot = run_root / "screenshots" / "B-peer-revision-open.png"
        peer_shot.parent.mkdir(parents=True, exist_ok=True)
        peer_shot.write_bytes(guest_b.screenshot(patience=45))
        peer_title = guest_b.active_window() or ""
        _save_json(run_root / "handoff_gui_evidence.json", {
            "run_id": run_id, "message_id": message["message_id"],
            "message_received_by_B": message["message_id"] in received_ids,
            "published_revision": a_revision, "peer_sha256": peer_sha,
            "peer_guest_path": peer_path, "active_window": peer_title,
            "screenshot": str(peer_shot.relative_to(run_root)),
            "gui_open_trace": _trace_actions(run_root, b_read_result),
        })

        order_edit_at = time.time()
        b_result = core._run_actor("B", guest_b, spec.AGENT_B_INSTRUCTION,
            scripted["B_order"], run_root, max_steps=10, case_id=spec.CASE_ID)
        if b_result.get("status") != "done":
            raise RuntimeError(f"scripted B order GUI control ended as {b_result.get('status')}")
        b_revision = bridge.publish("B")
        order_saved_at = time.time()
        gui_trace = _trace_actions(run_root, b_read_result)
        handoff = adapter.verify_handoff(
            revision=a_revision, peer_sha256=peer_sha,
            received_message_ids=received_ids, message_id=message["message_id"],
            peer_guest_path=peer_path, gui_action_trace=gui_trace,
            active_window=peer_title, screenshot_path=peer_shot,
            published_at=published_at, message_received_at=message_received_at,
            gui_read_at=gui_read_at, order_edit_at=order_edit_at,
            order_saved_at=order_saved_at)
        _save_json(run_root / "handoff_gate.json", handoff)
        bridge.stop()
        bridge_diagnostics = bridge.diagnostics()
        sync_result = {"final_versions": bridge.snapshot(), "transient_errors": bridge.errors,
                       "diagnostics": bridge_diagnostics,
                       "verified": (not bridge.errors and
                                    not bridge_diagnostics["infrastructure_review_required"])}
        _save_json(run_root / "workspace_sync_result.json", sync_result)
        bridge = None

        artifact_items = [
            {"actor": "A", "guest_id": guest_a.guest_key, "guest_path": a_path,
             "local_path": "A/forecast.ods"},
            {"actor": "B", "guest_id": guest_b.guest_key, "guest_path": b_path,
             "local_path": "B/order_plan.ods"},
        ]
        artifacts = collect_artifacts(run_root, artifact_items,
            core.GuestFiles({g.guest_key: g.env.controller for g in guests.values()}))
        score = oracle.evaluate(fixture / spec.FIXTURE_NAMES["forecast"],
            run_root / "artifacts/A/forecast.ods",
            fixture / spec.FIXTURE_NAMES["order"], run_root / "artifacts/B/order_plan.ods")
        _save_json(run_root / "oracle.json", score)

        reopen = []
        for role, guest, path in (("A", guest_a, a_path), ("B", guest_b, b_path)):
            data_before = guest.env.controller.get_file(path)
            _activate_calc(guest, path)
            guest.actor = "system"
            guest.run_pyautogui("import pyautogui, time; pyautogui.hotkey('ctrl','w'); time.sleep(2)")
            discarded = core._discard_postscore_unsaved_dialog(guest, f"v13-reopen-{role}")
            _launch_calc(guest, path, run_id)
            data_after = guest.env.controller.get_file(path)
            reopen.append({"role": role, "guest": guest.guest_key,
                "same_bytes": data_before == data_after,
                "sha256": adapter.sha256_bytes(data_after),
                "discarded_uncommitted_buffer_after_scoring": discarded})
        _save_json(run_root / "reopen_evidence.json", reopen)
        postscore_ok = shared_pilot._postscore_lifecycle_ok(reopen)

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
                raise RuntimeError("reset did not replace the owned v1.3 Guest")
            core._shell(guests[key],
                f"test ! -e {spec.TASK_ROOT} && ! pgrep -x soffice.bin >/dev/null")
            container_ids[key] = new_container.id
            reset_evidence.append({"guest": key, "old": old_id, "new": new_container.id,
                                   "workspace_clean": True, "labels": labels})
        _save_json(run_root / "reset_evidence.json", reset_evidence)
        reset_ok = len(reset_evidence) == len(envs) and all(x["workspace_clean"] for x in reset_evidence)
        actor_results = {"A": a_result, "B": b_result, "B_peer_read": b_read_result}
        status = adapter.map_scripted_result(oracle_result=score, actor_results=actor_results,
            handoff=handoff, postscore_lifecycle_ok=postscore_ok, reset_ok=reset_ok,
            bridge_ok=sync_result["verified"])
        result = {"run_id": run_id, "case_id": spec.CASE_ID,
            "case_version": spec.CASE_VERSION, "condition": condition,
            "control": "negative" if negative else "positive", "model_called": False,
            "actor_results": actor_results, "A_revision": a_revision,
            "B_revision": b_revision, "handoff": handoff, "oracle": score,
            "artifact_manifest": artifacts, "reopen": reopen,
            "postscore_lifecycle_ok": postscore_ok, "reset": reset_evidence,
            "elapsed_s": time.time() - metadata["started_at"], "status": status,
            "guest_validation_status": "requires_real_invocation_and_review"}
        _save_json(run_root / "result.json", result)
        return result
    finally:
        resource_stop.set()
        resource_thread.join(timeout=10)
        if bridge is not None:
            try:
                bridge.stop()
            except Exception as exc:
                with (run_root / "workspace_sync_errors.jsonl").open("a") as stream:
                    stream.write(json.dumps({"error": str(exc), "time": time.time()}) + "\n")
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
                with (run_root / "cleanup_errors.jsonl").open("a") as stream:
                    stream.write(json.dumps({"guest": key, "error": str(exc)}) + "\n")
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
        if cleanup_errors:
            raise RuntimeError("run-owned Guest cleanup incomplete: " + "; ".join(cleanup_errors))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-version", required=True, choices=("1.3.0",))
    parser.add_argument("--condition", required=True,
                        choices=("collaborative_shared", "collaborative_isolated"))
    parser.add_argument("--control", required=True, choices=("positive", "negative"))
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--provider", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--runtime", required=True)
    args = parser.parse_args(argv)
    try:
        result = _guest_controls(args.case_version, args.condition, args.run_root,
            args.provider.resolve(), args.image, args.runtime,
            negative=args.control == "negative")
    except Exception as exc:
        run_root = args.run_root.resolve()
        failure = {"status": "INVALID_INFRA_OR_RUNNER_ERROR",
                   "run_id": args.run_root.name, "case_version": args.case_version,
                   "error": f"{type(exc).__name__}: {exc}",
                   "traceback": traceback.format_exc(),
                   "model_called": False}
        if run_root.exists():
            _save_json(run_root / "failure.json", failure)
        print(json.dumps(failure, indent=2), file=sys.stderr)
        raise SystemExit(3)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 2)


if __name__ == "__main__":
    main()
