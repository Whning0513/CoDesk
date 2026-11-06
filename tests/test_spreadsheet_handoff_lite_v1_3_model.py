"""Offline contract, score, reopen, handoff and tool-boundary tests for v1.3."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from oscombo.collab.lite_file_guest_pilot import _postscore_lifecycle_ok
from oscombo.collab.spreadsheet_handoff_lite_v1_3 import model_pilot, spec


def _contract(arm):
    return model_pilot.model_contract(
        arm, model="test-model", base_url="https://model.invalid/v1",
        api_key_env="CASE6_TEST_KEY", mcp_python="/venv/bin/python")


def test_tri_arm_contract_pins_same_task_prompt_fixture_and_budget():
    contracts = {arm: _contract(arm) for arm in model_pilot.ARM_CONDITIONS}
    for key in ("case_id", "case_version", "model", "base_url", "api_key_env", "mcp_python",
                "effort", "model_timeout_s", "request_retries", "role_budget",
                "yield_wait_lifecycle", "actor_mcp_only", "actor_prompts_sha256",
                "fixture_names", "outputs"):
        assert len({json.dumps(item[key], sort_keys=True) for item in contracts.values()}) == 1
    assert contracts["isolated"]["guest_count"] == 2
    assert contracts["shared"]["guest_count"] == contracts["sharedlock"]["guest_count"] == 1
    assert contracts["shared"]["condition"] == contracts["sharedlock"]["condition"] == "collaborative_shared"
    assert contracts["isolated"]["gui_input_lock"] is False
    assert contracts["shared"]["gui_input_lock"] is False
    assert contracts["sharedlock"]["gui_input_lock"] is True


def test_small_isolated_pilot_budget_is_explicit_and_does_not_change_formal_budget():
    formal = _contract("isolated")
    pilot = model_pilot.model_contract(
        "isolated", model="test-model", base_url="https://model.invalid/v1",
        api_key_env="CASE6_TEST_KEY", mcp_python="/venv/bin/python",
        pilot_step_limit=8)
    assert formal["execution_mode"] == "formal"
    assert formal["role_budget"] == {"A": {"steps": 18, "model_tokens": None},
                                     "B": {"steps": 18, "model_tokens": None}}
    assert pilot["execution_mode"] == "diagnostic_pilot"
    assert pilot["pilot_step_limit"] == 8
    assert pilot["model_runner_version"] == "1.3.2"
    assert pilot["role_budget"] == {"A": {"steps": 8, "model_tokens": None},
                                    "B": {"steps": 8, "model_tokens": None}}
    assert spec.ROLE_BUDGET == {"A": {"steps": 18, "model_tokens": None},
                                "B": {"steps": 18, "model_tokens": None}}
    with pytest.raises(ValueError, match="Isolated-only"):
        model_pilot.model_contract(
            "shared", model="test-model", base_url="https://model.invalid/v1",
            api_key_env="CASE6_TEST_KEY", mcp_python="/venv/bin/python",
            pilot_step_limit=8)
    for invalid in (True, 3, 13, 8.0):
        with pytest.raises(ValueError, match="pilot step limit"):
            model_pilot.model_contract(
                "isolated", model="test-model", base_url="https://model.invalid/v1",
                api_key_env="CASE6_TEST_KEY", mcp_python="/venv/bin/python",
                pilot_step_limit=invalid)


def test_model_contract_has_no_disable_switch_for_request_allowlist():
    contract = _contract("shared")
    assert contract["actor_mcp_only"] is True
    assert "allowlist" not in contract or contract["allowlist"] is not False
    assert "tools" not in contract


def test_model_entry_rejects_preexisting_run_root_before_guest_or_api(monkeypatch, tmp_path):
    monkeypatch.setenv("CASE6_TEST_KEY", "offline-sentinel")
    run_root = tmp_path / "existing-run"
    run_root.mkdir()
    with pytest.raises(FileExistsError, match="run root already exists"):
        model_pilot.run_model_episode(
            arm="shared", run_root=run_root, provider=tmp_path, image="image.qcow2",
            runtime="runtime:tag", model="test-model", base_url="https://model.invalid/v1",
            api_key_env="CASE6_TEST_KEY", mcp_python="/venv/bin/python")


def test_robase_model_mode_requires_all_frozen_resource_pins(monkeypatch, tmp_path):
    monkeypatch.setenv("CASE6_TEST_KEY", "offline-sentinel")
    monkeypatch.delenv("CODESK_CASE6_V13_GUEST_IMAGE_SHA256", raising=False)
    monkeypatch.delenv("CODESK_CASE6_V13_RUNTIME_IMAGE_ID", raising=False)
    monkeypatch.delenv("CODESK_CASE6_V13_OSWORLD_COMMIT", raising=False)
    monkeypatch.delenv("CODESK_CASE6_V13_OSWORLD_DIFF_SHA256", raising=False)
    run_root = tmp_path / "not-started"
    with pytest.raises(RuntimeError, match="requires frozen image/runtime/OSWorld source pins"):
        model_pilot.run_model_episode(
            arm="shared", run_root=run_root, provider=tmp_path, image="image.qcow2",
            runtime="runtime:tag", model="test-model", base_url="https://model.invalid/v1",
            api_key_env="CASE6_TEST_KEY", mcp_python="/venv/bin/python",
            robase_validation=True)
    assert not run_root.exists()


def test_osworld_source_pin_hashes_tracked_diff_and_rejects_untracked_files(tmp_path):
    repo = tmp_path / "osworld"
    repo.mkdir()
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    (repo / "tracked.txt").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
    subprocess.run([
        "git", "-C", str(repo), "-c", "user.name=Offline Test",
        "-c", "user.email=offline@example.invalid", "commit", "--quiet", "-m", "pin",
    ], check=True)
    identity = model_pilot.osworld_source_identity(repo)
    commit, diff_sha = identity["commit"], identity["diff_sha256"]
    assert model_pilot.osworld_source_matches(commit, diff_sha, identity)
    assert not model_pilot.osworld_source_matches("0" * len(commit), diff_sha, identity)
    assert not model_pilot.osworld_source_matches(commit, "not-a-sha256", identity)

    (repo / "tracked.txt").write_text("tracked change\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
    staged_identity = model_pilot.osworld_source_identity(repo)
    assert staged_identity["commit"] == commit
    assert staged_identity["diff_sha256"] != diff_sha
    assert model_pilot.osworld_source_matches(
        commit, staged_identity["diff_sha256"], staged_identity)

    (repo / "untracked.txt").write_text("uncommitted\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="untracked non-ignored"):
        model_pilot.osworld_source_identity(repo)


def test_robase_model_entry_rejects_mismatched_osworld_commit_before_run_root(monkeypatch, tmp_path):
    repo = tmp_path / "osworld"
    repo.mkdir()
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    (repo / "tracked.txt").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
    subprocess.run([
        "git", "-C", str(repo), "-c", "user.name=Offline Test",
        "-c", "user.email=offline@example.invalid", "commit", "--quiet", "-m", "pin",
    ], check=True)
    identity = model_pilot.osworld_source_identity(repo)
    monkeypatch.setenv("CASE6_TEST_KEY", "offline-sentinel")
    monkeypatch.setenv("CODESK_CASE6_V13_GUEST_IMAGE_SHA256", "a" * 64)
    monkeypatch.setenv("CODESK_CASE6_V13_RUNTIME_IMAGE_ID", "sha256:" + "b" * 64)
    monkeypatch.setenv("CODESK_CASE6_V13_OSWORLD_COMMIT", "0" * len(identity["commit"]))
    monkeypatch.setenv("CODESK_CASE6_V13_OSWORLD_DIFF_SHA256", identity["diff_sha256"])
    run_root = tmp_path / "not-started"
    with pytest.raises(RuntimeError, match="OSWorld source identity does not match"):
        model_pilot.run_model_episode(
            arm="shared", run_root=run_root, provider=repo, image="image.qcow2",
            runtime="runtime:tag", model="test-model", base_url="https://model.invalid/v1",
            api_key_env="CASE6_TEST_KEY", mcp_python="/venv/bin/python",
            robase_validation=True)
    assert not run_root.exists()


def test_triad_shell_does_not_precreate_python_owned_run_root():
    script = Path(model_pilot.__file__).with_name("run_model_triad.sh").read_text()
    assert "--robase-validation" not in script
    assert 'mkdir -p "$run_root"' not in script
    assert '> "$CODESK_CASE6_V13_RUN_BASE/$run_id.runner.log"' in script
    assert '--run-root "$run_root"' in script
    assert 'case6_docker_host="${DOCKER_HOST:-unix:///var/run/docker.sock}"' in script
    assert "docker info --format '{{.DockerRootDir}}'" in script
    assert "docker image inspect" in script
    assert "CODESK_CASE6_V13_RUNTIME_IMAGE_ID" in script
    assert "docker run" not in script
    assert "docker pull" not in script
    assert "PYTHONDONTWRITEBYTECODE=1" in script
    assert "docker_data_root_matches" in script
    assert "docker_image_id_matches" in script
    assert '"$CODESK_CASE6_V13_DOCKER_DATA_ROOT" "$case6_actual_data_root"' in script
    assert "filesystem_capacity.tsv" in script
    assert "case6_check_fs 'run base'" in script
    assert "case6_check_fs 'Docker data-root'" in script
    assert "case6_check_fs 'Git common directory'" in script
    assert "case6_check_fs 'Guest image'" in script


def test_model_cli_has_explicit_small_pilot_cap_and_full_formal_default():
    source = Path(model_pilot.__file__).read_text(encoding="utf-8")
    assert 'parser.add_argument("--pilot-step-limit"' in source
    assert 'MODEL_RUNNER_VERSION = "1.3.2"' in source
    assert "max_steps=int(contract[\"role_budget\"][role][\"steps\"])" in source


def test_robase_wrapper_has_isolated_only_pilot_mode_and_preserves_formal_arms():
    script = Path(model_pilot.__file__).with_name("run_model_triad_robase.sh").read_text()
    assert 'case6_arms=(isolated shared sharedlock)' in script
    assert 'case6_arms=(isolated)' in script
    assert 'model_args+=(--pilot-step-limit "$case6_pilot_step_limit")' in script
    assert 'pilot_manifest.tsv' in script


def test_resource_gates_reject_wrong_docker_root_and_unpinned_runtime_digest():
    assert model_pilot.docker_data_root_matches("/data2/case6-docker/data", "/data2/case6-docker/data")
    assert not model_pilot.docker_data_root_matches("/data2/case6-docker/data", "/data3/.codesk-docker/data")
    assert not model_pilot.docker_data_root_matches("/data3/.codesk-docker/data", "/data3/.codesk-docker/data")
    good_id = "sha256:" + "a" * 64
    assert model_pilot.docker_image_id_matches(good_id, good_id)
    assert not model_pilot.docker_image_id_matches(good_id, "sha256:" + "b" * 64)
    assert not model_pilot.docker_image_id_matches("mutable:tag", "mutable:tag")


def test_desktopenv_and_setup_cache_must_be_run_owned(tmp_path):
    run_root = tmp_path / "run"
    owned_cache = run_root / "cache" / "A"
    owned_cache.mkdir(parents=True)
    env = SimpleNamespace(cache_dir_base=str(owned_cache),
                          setup_controller=SimpleNamespace(cache_dir=str(owned_cache)),
                          cache_dir=str(owned_cache / "task-123"))
    evidence = model_pilot.verify_run_owned_cache(env, run_root, "A", stage="boot")
    assert evidence["verified"] is True
    assert evidence["desktop_env_task_cache_dir"] == str(owned_cache / "task-123")

    env.setup_controller.cache_dir = str(owned_cache / "task-123")
    evidence = model_pilot.verify_run_owned_cache(env, run_root, "A", stage="boot")
    assert evidence["setup_controller_cache_dir"] == str(owned_cache / "task-123")

    env.setup_controller.cache_dir = str(tmp_path / "outside")
    with pytest.raises(ValueError, match="SetupController.cache_dir is outside"):
        model_pilot.verify_run_owned_cache(env, run_root, "A", stage="boot")


def test_boot_allows_missing_task_cache_but_reset_requires_it(tmp_path):
    run_root = tmp_path / "run"
    owned_cache = run_root / "cache" / "A"
    owned_cache.mkdir(parents=True)
    env = SimpleNamespace(cache_dir_base=str(owned_cache),
                          setup_controller=SimpleNamespace(cache_dir=str(owned_cache)))

    boot = model_pilot.verify_run_owned_cache(env, run_root, "A", stage="boot")
    assert boot["verified"] is True
    assert boot["desktop_env_task_cache_dir"] is None
    with pytest.raises(ValueError, match="missing after reset"):
        model_pilot.verify_run_owned_cache(env, run_root, "A", stage="reset")


def test_reset_task_cache_must_be_inside_guest_run_owned_cache(tmp_path):
    run_root = tmp_path / "run"
    owned_cache = run_root / "cache" / "A"
    owned_cache.mkdir(parents=True)
    env = SimpleNamespace(cache_dir_base=str(owned_cache),
                          setup_controller=SimpleNamespace(cache_dir=str(owned_cache)),
                          cache_dir=str(tmp_path / "outside-task-cache"))
    with pytest.raises(ValueError, match="task cache escapes"):
        model_pilot.verify_run_owned_cache(env, run_root, "A", stage="reset")

    env.cache_dir = str(owned_cache / "task-123")
    reset = model_pilot.verify_run_owned_cache(env, run_root, "A", stage="reset")
    assert reset["verified"] is True
    assert reset["desktop_env_task_cache_dir"] == str(owned_cache / "task-123")

    with pytest.raises(ValueError, match="stage must be"):
        model_pilot.verify_run_owned_cache(env, run_root, "A", stage="postscore")


def test_current_guest_mount_overlay_cache_and_runtime_pin_are_verified(tmp_path, monkeypatch):
    run_root = tmp_path / "run"
    owned_cache = run_root / "cache" / "A"
    overlay = run_root / "overlay" / "A" / "base.qcow2"
    owned_cache.mkdir(parents=True)
    overlay.parent.mkdir(parents=True)
    overlay.write_bytes(b"overlay")
    image = tmp_path / "guest.qcow2"
    image.write_bytes(b"immutable base")
    expected_runtime = "sha256:" + "a" * 64
    mount = {"Source": str(image), "Destination": "/System.qcow2", "RW": False}
    container = SimpleNamespace(id="c" * 64, attrs={"Mounts": [mount], "Image": expected_runtime})
    env = SimpleNamespace(
        provider=SimpleNamespace(_oscombo_overlay=str(overlay)),
        cache_dir_base=str(owned_cache),
        setup_controller=SimpleNamespace(cache_dir=str(owned_cache)),
        cache_dir=str(owned_cache / "task-123"))
    monkeypatch.setenv("CODESK_CASE6_V13_RUNTIME_IMAGE_ID", expected_runtime)

    evidence = model_pilot.verify_run_owned_guest_resources(
        container, env, str(image), run_root, "A", stage="boot")
    assert evidence["verified"] is True
    assert evidence["runtime_image_id"] == expected_runtime
    assert evidence["base_mount"]["RW"] is False
    assert evidence["validation_stage"] == "boot"

    env.cache_dir = None
    with pytest.raises(ValueError, match="missing after reset"):
        model_pilot.verify_run_owned_guest_resources(
            container, env, str(image), run_root, "A", stage="reset")
    env.cache_dir = str(owned_cache / "task-123")
    reset_evidence = model_pilot.verify_run_owned_guest_resources(
        container, env, str(image), run_root, "A", stage="reset")
    assert reset_evidence["verified"] is True
    assert reset_evidence["validation_stage"] == "reset"

    mount["RW"] = True
    with pytest.raises(ValueError, match="read-only"):
        model_pilot.verify_run_owned_guest_resources(
            container, env, str(image), run_root, "A", stage="boot")
    mount["RW"] = False
    container.attrs["Image"] = "sha256:" + "b" * 64
    with pytest.raises(ValueError, match="runtime image ID"):
        model_pilot.verify_run_owned_guest_resources(
            container, env, str(image), run_root, "A", stage="boot")


def test_each_filesystem_needs_15_gib_and_1024_free_inodes():
    assert model_pilot.filesystem_capacity_ok(15 * 1024 * 1024, 1024)
    assert not model_pilot.filesystem_capacity_ok(15 * 1024 * 1024 - 1, 1024)
    assert not model_pilot.filesystem_capacity_ok(15 * 1024 * 1024, 1023)


def test_runner_emits_mcp_wrapper_without_bytecode_writes(tmp_path):
    wrapper = Path(model_pilot._write_no_bytecode_python(tmp_path, "/data3/osworld/.venv/bin/python"))
    assert wrapper.is_file()
    assert wrapper.stat().st_mode & 0o777 == 0o700
    body = wrapper.read_text()
    assert "PYTHONDONTWRITEBYTECODE=1" in body
    assert "exec /data3/osworld/.venv/bin/python \"$@\"" in body




def _write_calls(root: Path, role: str, calls: list[tuple[str, object]]):
    session_root = root / "actor_runs" / role / role / "codex_home" / "sessions" / "2026"
    session_root.mkdir(parents=True, exist_ok=True)
    records = []
    for name, arguments in calls:
        records.append({"type": "response_item", "payload": {
            "type": "function_call", "name": name,
            "arguments": json.dumps(arguments) if isinstance(arguments, dict) else arguments}})
    (session_root / "session.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")


def test_actor_tool_boundary_fails_closed_on_missing_session_or_extra_tool(tmp_path):
    result = model_pilot.audit_actor_tool_boundary(tmp_path)
    assert not result["valid"]
    _write_calls(tmp_path, "A", [("screenshot", {})])
    _write_calls(tmp_path, "B", [("apply_patch", {"file": "x"})])
    result = model_pilot.audit_actor_tool_boundary(tmp_path)
    assert not result["valid"]
    assert "actor_used_tools_outside_contract:B" in result["errors"]


def _good_handoff_root(root: Path):
    peer_path = "/tmp/sh13/incoming/A/forecast-r000001.ods"
    _write_calls(root, "A", [("mcp__desktop.screenshot", {}),
                               ("mcp__desktop.type_text", {"text": "=formula"}),
                               ("mcp__collaboration.publish_saved_artifact", {})])
    _write_calls(root, "B", [
        ("mcp__desktop.screenshot", {}),
        ("mcp__collaboration.list_saved_artifacts", {}),
        ("mcp__collaboration.read_messages", {}),
        ("mcp__desktop.key", {"key": "CTRL+O"}),
        ("mcp__desktop.type_text", {"text": peer_path}),
        ("mcp__desktop.key", {"key": "ENTER"}),
        ("mcp__desktop.screenshot", {}),
        ("mcp__desktop.key", {"key": "ALT+TAB"}),
        ("mcp__collaboration.publish_saved_artifact", {}),
    ])
    b_actor_dir = root / "actor_runs" / "B" / "B"
    b_actor_dir.mkdir(parents=True, exist_ok=True)
    (b_actor_dir / "stdout.log").write_text(json.dumps({
        "type": "item.completed", "item": {"server": "collaboration",
            "tool": "read_messages", "result": {"structured_content": {
                "result": [{"message_id": "ready-1"}]}}}}) + "\n")
    bridge = root / "workspace_versions"
    bridge.mkdir()
    (bridge / "events.jsonl").write_text(json.dumps({
        "event": "revision_committed", "actor": "A", "revision": 1,
        "time": 10.0, "sha256": "a" * 64}) + "\n" + json.dumps({
        "event": "peer_view_verified", "actor": "A", "peer": "B", "revision": 1,
        "time": 10.1, "mode": "444"}) + "\n")
    bridge_snapshot = {
        "A": {"actor": "A", "revision": 1, "delivered": True,
              "peer_view_path": "incoming/A/forecast-r000001.ods", "sha256": "a" * 64},
        "B": {"actor": "B", "revision": 1, "delivered": True,
              "peer_view_path": "incoming/B/order_plan-r000001.ods", "sha256": "b" * 64},
    }
    protocol = [{"type": "message", "actor": "A", "recipient": "B",
                 "timestamp": 11.0, "message_id": "ready-1", "body": "Saved forecast is ready."}]
    return bridge_snapshot, protocol


def test_model_handoff_gate_requires_revision_message_gui_open_and_b_save(tmp_path):
    snapshot, events = _good_handoff_root(tmp_path)
    result = model_pilot.audit_model_handoff(tmp_path, snapshot, events)
    assert result["valid"], result
    assert result["visual_review_required"] is True
    assert all(result["checks"].values())


def test_model_handoff_gate_rejects_hash_only_or_numeric_message(tmp_path):
    snapshot, events = _good_handoff_root(tmp_path)
    events[0]["body"] = "The result is 73; ready."
    result = model_pilot.audit_model_handoff(tmp_path, snapshot, events)
    assert not result["valid"]
    assert not result["checks"]["A_message_has_no_numeric_answer"]
    snapshot["A"]["peer_view_path"] = "incoming/A/forecast-r000002.ods"
    result = model_pilot.audit_model_handoff(tmp_path, snapshot, events)
    assert not result["checks"]["B_typed_exact_peer_revision_path"]


def test_model_handoff_gate_requires_b_to_observe_the_ready_message(tmp_path):
    snapshot, events = _good_handoff_root(tmp_path)
    (tmp_path / "actor_runs" / "B" / "B" / "stdout.log").write_text("")
    result = model_pilot.audit_model_handoff(tmp_path, snapshot, events)
    assert not result["valid"]
    assert not result["checks"]["B_received_A_ready_message_in_tool_result"]


def test_readiness_message_allows_revision_numbers_dates_and_versions():
    assert not model_pilot._message_discloses_business_quantity(
        "Saved revision r000001 on 2026-11-06; forecast file is ready.")
    assert not model_pilot._message_discloses_business_quantity(
        "Version 1.3.0 saved; ready for review.")
    assert model_pilot._message_discloses_business_quantity(
        "Forecast result: 73 units.")
    assert model_pilot._message_discloses_business_quantity(
        "The result is seventy-three units.")


def test_postscore_reopen_gate_checks_saved_bytes_and_missing_output_classification():
    assert _postscore_lifecycle_ok([
        {"role": "A", "same_bytes": True}, {"role": "B", "same_bytes": True}])
    assert not _postscore_lifecycle_ok([
        {"role": "A", "same_bytes": True}, {"role": "B", "same_bytes": False}])
    assert not _postscore_lifecycle_ok([
        {"role": "A", "same_bytes": True, "gui_reopen": "skipped_unsaved_buffer"},
        {"role": "B", "same_bytes": True}])
    # A task-level missing output is not confused with failed reopening of a saved artifact.
    assert _postscore_lifecycle_ok([
        {"role": "A", "same_bytes": True}, {"role": "B", "missing_output": True}])


def test_model_score_mapping_separates_task_failure_from_infrastructure_failure():
    relay = {"valid": True}
    boundary = {"valid": True}
    actors = {"A": {"status": "done", "steps": 3}, "B": {"status": "done", "steps": 5}}
    handoff = {"valid": True}
    common = {"actor_results": actors, "handoff": handoff, "bridge_ok": True,
              "relay_audit": relay, "actor_tool_audit": boundary,
              "postscore_lifecycle_ok": True, "reset_ok": True}
    assert model_pilot.map_model_result(oracle_result={"joint_success": True}, **common) == "PASS"
    assert model_pilot.map_model_result(oracle_result={"joint_success": False}, **common) == "FAIL"
    assert model_pilot.map_model_result(oracle_result={"joint_success": True},
        **{**common, "handoff": {"valid": False}}) == "FAIL"
    assert model_pilot.map_model_result(oracle_result={"joint_success": True},
        **{**common, "bridge_ok": False}) == "INVALID_INFRA_OR_RUNNER_ERROR"
    assert model_pilot.map_model_result(oracle_result={"joint_success": True},
        **{**common, "relay_audit": {"valid": False}}) == "INVALID_INFRA_OR_RUNNER_ERROR"
    assert model_pilot.map_model_result(oracle_result={"joint_success": True},
        **{**common, "actor_tool_audit": {"valid": False}}) == "INVALID_INFRA_OR_RUNNER_ERROR"
    assert model_pilot.map_model_result(oracle_result={"joint_success": True},
        **{**common, "postscore_lifecycle_ok": False}) == "INVALID_INFRA_OR_RUNNER_ERROR"
    assert model_pilot.map_model_result(oracle_result={"joint_success": True},
        **{**common, "reset_ok": False}) == "INVALID_INFRA_OR_RUNNER_ERROR"
    assert model_pilot.map_model_result(oracle_result={"joint_success": True},
        **{**common, "actor_results": {"A": {"status": "error"}, "B": actors["B"]}}) == "INVALID_INFRA_OR_RUNNER_ERROR"


def test_overlap_summary_excludes_b_wait_period_and_reports_observed_gui_overlap():
    summary = model_pilot.compute_overlap_summary(
        relay_events=[
            {"actor": "A", "started_at": 0.0, "time": 5.0},
            {"actor": "A", "started_at": 7.0, "time": 8.0},
            {"actor": "B", "started_at": 2.0, "time": 4.0},
            {"actor": "B", "started_at": 9.0, "time": 10.0},
        ],
        gui_actions=[
            {"actor": "A", "started_at": 7.0, "ended_at": 9.0},
            {"actor": "B", "started_at": 9.0, "ended_at": 10.0},
        ],
        lifecycle_events=[
            {"actor": "B", "event": "suspended_for_peer_handoff", "time": 4.0},
            {"actor": "B", "event": "woken_by_peer_handoff", "time": 8.0},
        ],
        actor_results={
            "A": {"started_at": 0.0, "ended_at": 9.0},
            "B": {"started_at": 1.0, "ended_at": 10.0},
        })
    assert summary["wall_clock_interval_overlap_s"] == 8.0
    assert summary["suspended_wait_s"]["B"] == 4.0
    assert summary["observed_active_request_or_gui_overlap_s"] == 2.0
    assert summary["observed_shared_gui_action_overlap_s"] == 0.0
    assert "local model deliberation" in summary["active_overlap_scope"]


def test_model_source_does_not_change_v13_task_prompt_or_role_budget():
    assert spec.ROLE_BUDGET == {"A": {"steps": 18, "model_tokens": None},
                                "B": {"steps": 18, "model_tokens": None}}
    assert "forecast" in spec.AGENT_A_INSTRUCTION
    assert "cartons" in spec.AGENT_B_INSTRUCTION.lower()
