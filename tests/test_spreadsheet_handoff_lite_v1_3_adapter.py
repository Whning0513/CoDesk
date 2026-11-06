"""Offline tests for Case 6 v1.3 adapter selection and gates.

These tests mock no Guest because they only exercise pure adapter contracts;
they do not establish that the Guest entry point has run successfully.
"""
from __future__ import annotations

import pytest

from oscombo.collab.spreadsheet_handoff_lite_v1_3 import (
    adapter, fixtures, live_pilot, oracle, spec,
)


def _valid_handoff(tmp_path):
    screenshot = tmp_path / "peer-view.png"
    screenshot.write_bytes(b"offline placeholder image bytes")
    peer_path = f"{spec.TASK_ROOT}/incoming/A/forecast-r000001.ods"
    sha = "a" * 64
    revision = {"actor": "A", "revision": 1, "sha256": sha,
                "peer_view_path": "incoming/A/forecast-r000001.ods", "delivered": True}
    trace = [
        {"code": "pyautogui.hotkey('ctrl','o')"},
        {"code": f"pyautogui.write({peer_path!r}, interval=0.02)"},
    ]
    result = adapter.verify_handoff(
        revision=revision, peer_sha256=sha, received_message_ids={"m-a-ready"},
        message_id="m-a-ready", peer_guest_path=peer_path, gui_action_trace=trace,
        active_window="forecast-r000001.ods - LibreOffice Calc", screenshot_path=screenshot,
        published_at=1.0, message_received_at=2.0, gui_read_at=3.0,
        order_edit_at=4.0, order_saved_at=5.0)
    return result, revision, peer_path, trace, screenshot


def test_selector_is_pinned_to_v1_3_spec_fixture_and_oracle():
    selected = adapter.select_case("1.3.0")
    assert selected == (spec, fixtures, oracle)
    with pytest.raises(ValueError, match="unsupported Spreadsheet Handoff version"):
        adapter.select_case("1.2.0")
    with pytest.raises(ValueError, match="unsupported Spreadsheet Handoff version"):
        adapter.select_case("latest")


def test_cli_selects_the_v1_3_scripted_entry_without_starting_a_guest(monkeypatch, tmp_path):
    observed = {}

    def fake_controls(version, condition, run_root, provider, image, runtime, negative=False):
        observed.update(version=version, condition=condition, negative=negative)
        return {"status": "PASS", "model_called": False}

    monkeypatch.setattr(live_pilot, "_guest_controls", fake_controls)
    args = ["--case-version", "1.3.0", "--condition", "collaborative_shared",
            "--control", "negative", "--run-root", str(tmp_path / "new-run-123"),
            "--provider", str(tmp_path / "provider"), "--image", "guest.qcow2",
            "--runtime", "runtime:offline"]
    with pytest.raises(SystemExit) as stopped:
        live_pilot.main(args)
    assert stopped.value.code == 0
    assert observed == {"version": "1.3.0", "condition": "collaborative_shared",
                        "negative": True}


def test_scripted_controls_are_version_specific_and_have_expected_control_shape():
    positive = adapter.scripted_actions(False)
    negative = adapter.scripted_actions(True)
    assert set(positive) == {"A", "B_read", "B_order"}
    assert positive["A"][0] != negative["A"][0]
    assert "'73'" in positive["B_order"][1]
    assert "'8'" in positive["B_order"][2]
    assert "'65'" in negative["B_order"][1]
    assert "'7'" in negative["B_order"][2]
    assert all("gold" not in action.lower() and "oracle" not in action.lower()
               for actions in positive.values() for action in actions)
    with pytest.raises(ValueError, match="peer revision must be inside"):
        adapter.peer_read_actions("/tmp/other/forecast.ods")


def test_handoff_gate_requires_message_exact_peer_bytes_gui_open_and_order(tmp_path):
    result, _, _, _, _ = _valid_handoff(tmp_path)
    assert result["valid"]
    assert result["reasons"] == []


@pytest.mark.parametrize("change,reason", [
    ({"peer_sha256": "b" * 64}, "peer_revision_bytes_do_not_match"),
    ({"received_message_ids": set()}, "A_ready_message_not_received_by_B"),
    ({"gui_action_trace": []}, "GUI_trace_does_not_open_exact_peer_revision"),
    ({"revision": {"actor": "A", "revision": 2, "sha256": "a" * 64,
                   "peer_view_path": "incoming/A/forecast-r000001.ods", "delivered": True}},
     "peer_view_filename_revision_mismatch"),
    ({"active_window": "order_plan.ods - Calc"}, "peer_revision_not_visible_in_active_GUI_window"),
    ({"gui_read_at": 0.5}, "handoff_and_order_edit_chronology_invalid"),
])
def test_handoff_gate_rejects_hash_only_or_incomplete_evidence(tmp_path, change, reason):
    _, revision, peer_path, trace, screenshot = _valid_handoff(tmp_path)
    kwargs = {"revision": revision, "peer_sha256": "a" * 64,
              "received_message_ids": {"m-a-ready"}, "message_id": "m-a-ready",
              "peer_guest_path": peer_path, "gui_action_trace": trace,
              "active_window": "forecast-r000001.ods - LibreOffice Calc",
              "screenshot_path": screenshot, "published_at": 1.0,
              "message_received_at": 2.0, "gui_read_at": 3.0,
              "order_edit_at": 4.0, "order_saved_at": 5.0}
    kwargs.update(change)
    result = adapter.verify_handoff(**kwargs)
    assert not result["valid"]
    assert reason in result["reasons"]


def test_scripted_result_mapping_separates_scored_failure_from_invalid_run(tmp_path):
    handoff, *_ = _valid_handoff(tmp_path)
    actors = {"A": {"status": "done"}, "B": {"status": "done"}}
    assert adapter.map_scripted_result(oracle_result={"joint_success": True},
        actor_results=actors, handoff=handoff, postscore_lifecycle_ok=True,
        reset_ok=True, bridge_ok=True) == "PASS"
    assert adapter.map_scripted_result(oracle_result={"joint_success": False},
        actor_results=actors, handoff=handoff, postscore_lifecycle_ok=True,
        reset_ok=True, bridge_ok=True) == "FAIL"
    assert adapter.map_scripted_result(oracle_result={"joint_success": True},
        actor_results=actors, handoff={"valid": False}, postscore_lifecycle_ok=True,
        reset_ok=True, bridge_ok=True) == "INVALID_INFRA_OR_RUNNER_ERROR"
    assert adapter.map_scripted_result(oracle_result={"joint_success": True},
        actor_results=actors, handoff=handoff, postscore_lifecycle_ok=False,
        reset_ok=True, bridge_ok=True) == "INVALID_INFRA_OR_RUNNER_ERROR"
    assert adapter.map_scripted_result(oracle_result={"joint_success": True},
        actor_results={"A": {"status": "error"}, "B": {"status": "done"}},
        handoff=handoff, postscore_lifecycle_ok=True, reset_ok=True,
        bridge_ok=True) == "INVALID_INFRA_OR_RUNNER_ERROR"
    assert adapter.map_scripted_result(oracle_result={"joint_success": True},
        actor_results=actors, handoff=handoff, postscore_lifecycle_ok=True,
        reset_ok=True, bridge_ok=False) == "INVALID_INFRA_OR_RUNNER_ERROR"
