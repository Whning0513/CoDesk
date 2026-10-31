"""Synthetic evidence tests; these do not claim a real Guest execution."""
import hashlib
import json
from pathlib import Path

import pytest

from oscombo.collab.workspace_assembly_lite_v2 import fixtures, freeze, oracle, resource_sampler, spec


def make_control(root: Path, *, negative=False):
    root.mkdir()
    fixtures.build_fixture(root / "fixtures", seed=freeze.CONTROL_SEED)
    tag = fixtures.tag_for_seed(freeze.CONTROL_SEED)
    for directory in ("artifacts/A", "artifacts/B", "workspace_versions", "collaboration", "shots", "trace"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    source = (root / "fixtures/inspection_note.txt").read_bytes()
    sha = hashlib.sha256(source).hexdigest()
    (root / "artifacts/A/inspection_note.txt").write_bytes(source)
    fixtures.report_odt(root / "artifacts/B/handoff_report.odt", "Audience: Operations.",
                        f"Attachment: inspection_note.txt; tag {'WRONG-00' if negative else tag}.")
    score = oracle.evaluate(root / "fixtures/inspection_note.txt", root / "artifacts/A/incoming/inspection_note.txt",
        root / "artifacts/A/inspection_note.txt", root / "fixtures/handoff_report.odt", root / "artifacts/B/handoff_report.odt")
    meta = {"run_id": root.name, "case_id": spec.CASE_ID, "case_version": spec.CASE_VERSION,
        "source_commit": "abc", "fixture_seed": freeze.CONTROL_SEED, "condition": "collaborative_shared",
        "guest_count": 1, "guests": [{"container_id": "guest1"}], "model_called": False,
        "guest_resources_requested": {"cpus": "8", "ram": "8G"},
        "scripted_negative_control": negative, "scripted_view_version_probe": False}
    (root / "provenance.json").write_text(json.dumps(meta))
    res = {"postscore_lifecycle_ok": True, "reopen_complete": True, "bridge_valid": True, "oracle_fixture_valid": True,
           "reopen": [{"role": "A", "same_bytes": True}, {"role": "B", "same_bytes": True}],
           "reset": [{"workspace_clean": True}], "status": "FAIL" if negative else "PASS", "oracle": score}
    (root / "result.json").write_text(json.dumps(res))
    (root / "missing_outputs.json").write_text("[]\n")
    (root / "oracle.json").write_text(json.dumps(score))
    view_path = "views/B/inspection_note-r000001.txt"
    sync = {"final_sync_succeeded": True, "verified": True,
        "diagnostics": {"infrastructure_review_required": False},
        "final_versions": {"A": {"revision": 1, "sha256": sha, "peer_view_path": view_path}}}
    (root / "workspace_sync_result.json").write_text(json.dumps(sync))
    fields = {"VmRSS": "10 kB", "VmSwap": "0 kB", "read_bytes": "0", "write_bytes": "0"}
    sample = {"guests": [{"container_id": "guest1", "argv": ["qemu-system-x86_64", "-m", "8G", "-smp", "8"],
                          "rss_and_io": fields}],
        "host_meminfo": {"MemAvailable": "1 kB", "SwapTotal": "1 kB", "SwapFree": "1 kB"},
        "host_io_pressure": "some avg10=0.00"}
    (root / "resource_samples_v2.jsonl").write_text(json.dumps(sample) + "\n")
    (root / "resource_audit.json").write_text(json.dumps(resource_sampler.summarize(root)))
    fixtures.report_odt(root / "control_prework.odt", "Audience: Operations.")
    (root / "control_prework.json").write_text(json.dumps({"sha256": freeze._sha(root / "control_prework.odt"),
        "finished_at": 5, "trace_path": "trace/pre.json"}))
    (root / "trace/pre.json").write_text("{}")
    (root / "trace/view.json").write_text("{}")
    (root / "shots/view.png").write_bytes(b"synthetic, not real GUI")
    (root / "view.txt").write_bytes(source)
    view = {"revision": 1, "peer_view_path": view_path, "sha256": sha, "mode": "444", "owner_mode": "644",
            "opened_at": 20, "window": "inspection_note-r000001.txt (read-only)",
            "trace_path": "trace/view.json", "screenshot": "shots/view.png", "recovered_copy": "view.txt"}
    (root / "control_B_peer_view.json").write_text(json.dumps(view))
    events = [{"event": "peer_view_verified", "actor": "A", "revision": 1, "sha256": sha, "mode": "444", "time": 9},
              {"event": "revision_committed", "actor": "A", "revision": 1, "sha256": sha, "time": 10}]
    (root / "workspace_versions/events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    (root / "collaboration/events.jsonl").write_text(json.dumps({"type": "message", "actor": "A",
        "timestamp": 15, "body": "Revision 1 is ready."}) + "\n")
    return tag


def test_freeze_control_checks_artifacts_chronology_and_leak(tmp_path):
    root = tmp_path / "positive"
    tag = make_control(root)
    assert freeze._control(root, "abc", "positive_shared")["status"] == "PASS"
    (root / "collaboration/events.jsonl").write_text(json.dumps({"type": "message", "actor": "A",
        "timestamp": 15, "body": f"Revision 1 tag is {tag}."}) + "\n")
    with pytest.raises(ValueError, match="leaks tag"):
        freeze._control(root, "abc", "positive_shared")


def test_freeze_control_rejects_resource_gap_and_wrong_negative(tmp_path):
    root = tmp_path / "negative"
    make_control(root, negative=True)
    assert freeze._control(root, "abc", "negative_shared")["status"] == "FAIL"
    data = json.loads((root / "resource_samples_v2.jsonl").read_text())
    data["guests"][0]["argv"][-1] = "4"
    (root / "resource_samples_v2.jsonl").write_text(json.dumps(data) + "\n")
    with pytest.raises(ValueError, match="resource audit"):
        freeze._control(root, "abc", "negative_shared")


def test_freeze_evidence_cannot_escape_run_root(tmp_path):
    root = tmp_path / "run"
    root.mkdir()
    (tmp_path / "outside").write_text("outside")
    with pytest.raises(ValueError, match="unsafe"):
        freeze._file(root, "../outside")


def test_missing_model_output_is_task_failure_when_other_reopens_succeed(tmp_path):
    root = tmp_path / "model-failure"
    make_control(root)
    (root / "artifacts/A/inspection_note.txt").unlink()
    score = oracle.evaluate(root / "fixtures/inspection_note.txt", root / "artifacts/A/incoming/inspection_note.txt",
        root / "artifacts/A/inspection_note.txt", root / "fixtures/handoff_report.odt", root / "artifacts/B/handoff_report.odt")
    result = json.loads((root / "result.json").read_text())
    result.update({"status": "FAIL", "oracle": score, "reopen_complete": False,
        "reopen": [{"role": "A", "same_bytes": False, "missing_output": True},
                   {"role": "B", "same_bytes": True}]})
    (root / "result.json").write_text(json.dumps(result))
    (root / "oracle.json").write_text(json.dumps(score))
    (root / "missing_outputs.json").write_text('["A"]\n')
    freeze._common(root, "abc", freeze.CONTROL_SEED, "shared", allow_missing_outputs=True)
    with pytest.raises(ValueError, match="unapproved missing output"):
        freeze._common(root, "abc", freeze.CONTROL_SEED, "shared")
