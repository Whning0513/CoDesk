"""Offline scheduling checks; synthetic outcomes are not Guest experiments."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from oscombo.collab.workspace_assembly_lite_v2 import campaign, freeze


def test_next_slot_preserves_fixed_order_and_never_replaces_valid_failure():
    state = {"attempts": []}
    assert campaign.expected_slot(state) == (1, "round1", "isolated")
    state["attempts"].append({"slot": 1, "round": "round1", "arm": "isolated", "status": "VALID_FAIL"})
    assert campaign.expected_slot(state) == (2, "round1", "shared")
    state["attempts"].append({"slot": 2, "round": "round1", "arm": "shared", "status": "NOT_STARTED"})
    assert campaign.expected_slot(state) == (2, "round1", "shared")
    state["attempts"].append({"slot": 2, "round": "round1", "arm": "shared", "status": "RUNNING"})
    with pytest.raises(RuntimeError, match="no terminal status"):
        campaign.expected_slot(state)
    state["attempts"][-1]["status"] = "VALID_PASS"
    state["attempts"][-1]["arm"] = "shared_lock"
    with pytest.raises(RuntimeError, match="frozen order"):
        campaign.expected_slot(state)


def test_formal_reservation_binds_freeze_round_arm_and_unique_run(tmp_path):
    frozen = tmp_path / "freeze.json"
    frozen.write_text(json.dumps({"formal_sequence": freeze.SEQUENCE}))
    state_path = tmp_path / "state.json"
    state = {"freeze_sha256": campaign._sha(frozen), "attempts": [{"slot": 1,
        "round": "round1", "arm": "isolated", "run_id": "wa-lite-v2-x", "status": "RUNNING"}]}
    state_path.write_text(json.dumps(state))
    campaign.verify_reservation(state_path, frozen, "wa-lite-v2-x", "round1", "isolated")
    with pytest.raises(RuntimeError, match="reservation"):
        campaign.verify_reservation(state_path, frozen, "wa-lite-v2-x", "round1", "shared")
    with pytest.raises(RuntimeError, match="reservation"):
        campaign.verify_reservation(state_path, frozen, "different", "round1", "isolated")


def test_classify_rejects_incomplete_evidence_without_counting_score(tmp_path):
    root = tmp_path / "run"
    assert campaign.classify(root, 3) == "NOT_STARTED"
    root.mkdir()
    result = {"status": "FAIL", "postscore_lifecycle_ok": True, "bridge_valid": True, "oracle_fixture_valid": True,
              "reopen_complete": True,
              "reopen": [{"role": "A", "same_bytes": True}, {"role": "B", "same_bytes": True}]}
    (root / "result.json").write_text(json.dumps(result))
    (root / "missing_outputs.json").write_text("[]\n")
    assert campaign.classify(root, 2) == "INVALID_INFRA"
    (root / "resource_audit.json").write_text(json.dumps({"valid": True}))
    (root / "contract_audit.json").write_text(json.dumps({"valid": True}))
    (root / "model_metrics_v2.json").write_text(json.dumps({"lifecycle_errors": []}))
    assert campaign.classify(root, 2) == "VALID_FAIL"
    result["reopen_complete"] = False
    result["reopen"][0] = {"role": "A", "same_bytes": False, "missing_output": True}
    (root / "missing_outputs.json").write_text('["A"]\n')
    (root / "result.json").write_text(json.dumps(result))
    assert campaign.classify(root, 2) == "VALID_FAIL"
    result["reopen"][0] = {"role": "A", "same_bytes": False, "postscore_error": "broken"}
    (root / "missing_outputs.json").write_text("[]\n")
    (root / "result.json").write_text(json.dumps(result))
    assert campaign.classify(root, 2) == "INVALID_INFRA"
    result["reopen_complete"] = True
    result["reopen"][0] = {"role": "A", "same_bytes": True}
    (root / "result.json").write_text(json.dumps(result))
    assert campaign.classify(root, 0) == "INVALID_INFRA"
    result["status"] = "PASS"
    (root / "result.json").write_text(json.dumps(result))
    assert campaign.classify(root, 0) == "VALID_PASS"
    (root / "failure.json").write_text("{}")
    assert campaign.classify(root, 0) == "INVALID_INFRA"


def test_interrupted_attempt_requires_dead_pid_and_no_owned_guest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    frozen = tmp_path / "freeze.json"
    frozen.write_text(json.dumps({"formal_sequence": freeze.SEQUENCE}))
    state_path = tmp_path / "state.json"
    state = {"freeze_sha256": campaign._sha(frozen), "attempts": [{"slot": 1,
        "round": "round1", "arm": "isolated", "run_id": "wa-lite-v2-test", "status": "RUNNING", "pid": 12345}]}
    state_path.write_text(json.dumps(state))
    review = tmp_path / "review.json"
    review.write_text(json.dumps({"run_id": "wa-lite-v2-test", "reason": "verified process exit", "reviewer": "operator"}))
    monkeypatch.setattr(campaign.os, "kill", lambda pid, sig: None)
    with pytest.raises(RuntimeError, match="still present"):
        campaign.resolve_interrupted(frozen, state_path, review)
    def gone(pid, sig):
        raise ProcessLookupError
    monkeypatch.setattr(campaign.os, "kill", gone)
    monkeypatch.setattr(campaign.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout="container-id\n"))
    with pytest.raises(RuntimeError, match="containers still exist"):
        campaign.resolve_interrupted(frozen, state_path, review)
    monkeypatch.setattr(campaign.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=""))
    result = campaign.resolve_interrupted(frozen, state_path, review)
    assert result["status"] == "NOT_STARTED"
