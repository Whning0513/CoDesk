"""Case 6 v1.2 rejects ambiguous model delivery without changing old runs."""
import json
import os
from pathlib import Path
import subprocess

from oscombo.collab.spreadsheet_handoff_lite_v1_2.relay_transport import (
    audit, audit_and_mark, relay_event_clean,
)


def event(actor):
    return {"actor": actor, "upstream_status": 200, "actor_mcp_only": True,
            "headers_sent": True, "forwarded_bytes": 32,
            "response_evidence_version": 1, "response_format": "sse",
            "response_terminal": "response.completed"}


def write(root, events):
    (root / "codex_relay_events.jsonl").write_text(
        "\n".join(json.dumps(item) for item in events) + "\n")


def test_all_events_require_completed_terminal_and_both_actors(tmp_path):
    good = [event("A"), event("B")]
    write(tmp_path, good)
    assert audit(tmp_path)["valid"]
    for bad in (
        {"actor": "B", "error_type": "BrokenPipeError", "upstream_status": 200},
        {**event("B"), "upstream_status": 500},
        {**event("B"), "response_terminal": "missing"},
        {**event("B"), "response_terminal": "response.failed"},
        {k: v for k, v in event("B").items() if k != "response_terminal"},
        {**event("B"), "forwarded_bytes": 0},
    ):
        write(tmp_path, good + [bad])
        assert not audit(tmp_path)["valid"]
        assert not relay_event_clean(bad)
    write(tmp_path, [event("A")])
    assert not audit(tmp_path)["valid"]
    write(tmp_path, good)
    with (tmp_path / "codex_relay_events.jsonl").open("a") as stream:
        stream.write("{incomplete\n")
    assert audit(tmp_path)["malformed_event_count"] == 1
    assert not audit(tmp_path)["valid"]


def test_invalid_relay_marks_new_result_but_preserves_original_oracle(tmp_path):
    result = {"status": "FAIL", "oracle": {"joint_success": False}, "reopen_complete": True}
    path = tmp_path / "result.json"
    path.write_text(json.dumps(result))
    write(tmp_path, [event("A"), {**event("B"), "response_terminal": "done_only"}])
    outcome = audit_and_mark(tmp_path)
    assert not outcome["valid"]
    marked = json.loads(path.read_text())
    assert marked["status"] == "INVALID_INFRA_OR_RUNNER_ERROR"
    assert marked["pre_transport_status"] == "FAIL"
    assert marked["oracle"] == result["oracle"]
    assert json.loads((tmp_path / "relay_transport_audit.json").read_text()) == outcome
    write(tmp_path, [event("A"), event("B")])
    path.write_text(json.dumps(result))
    assert audit_and_mark(tmp_path)["valid"]
    assert json.loads(path.read_text()) == result


def test_versioned_runner_stops_on_transport_invalid_without_guest(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    test_root = tmp_path / "episode"
    (test_root / "audits/three_lite_cases_20261029").mkdir(parents=True)
    provider = tmp_path / "provider"
    fake_python = provider / ".venv/bin/python"
    fake_python.parent.mkdir(parents=True)
    fake_python.write_text("#!/usr/bin/python3\n"
        "import json,os,pathlib,shutil,sys\n"
        "module=sys.argv[2] if len(sys.argv)>2 and sys.argv[1]=='-m' else ''\n"
        "if module.endswith('.live_pilot'):\n"
        " root=pathlib.Path(sys.argv[sys.argv.index('--run-root')+1]); root.mkdir(parents=True)\n"
        " (root/'result.json').write_text(json.dumps({'status':'FAIL','oracle':{'joint_success':False}}))\n"
        " shutil.copyfile(os.environ['CASE6_TEST_EVENTS'],root/'codex_relay_events.jsonl')\n"
        " sys.exit(2)\n"
        "if module.endswith('.relay_transport'):\n"
        " os.execv(os.environ['CASE6_REAL_PYTHON'],[os.environ['CASE6_REAL_PYTHON'],*sys.argv[1:]])\n"
        "sys.exit(0)\n")
    fake_python.chmod(0o700)
    config = tmp_path / "env.sh"
    config.write_text(f"export OSWORLD_DIR={provider}\n"
                      "export OSCOMBO_GUEST_IMAGE=/unused\nexport OSCOMBO_RUNTIME_IMAGE=unused\n")
    events = tmp_path / "events.jsonl"
    write(tmp_path, [event("A"), event("B"),
                     {"actor": "B", "error_type": "ChunkedEncodingError", "upstream_status": 200}])
    (tmp_path / "codex_relay_events.jsonl").replace(events)
    command = ("source \"$CASE6_RUN_COMMON\"; case6_root=\"$CASE6_TEST_ROOT\"; "
               "cd \"$case6_root\"; case6_preflight() { return 0; }; "
               "AIGCBEST_API_KEY=synthetic; case6_run_case model collaborative_shared fixture-run 1 || true; "
               "printf '%s %s\\n' \"$RUN_CASE_DRIVER_CODE\" \"$RUN_CASE_CODE\"")
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "CODESK_ENV_FILE": str(config),
           "CASE6_RUN_COMMON": str(repo / "oscombo/collab/spreadsheet_handoff_lite_v1_2/run_common.sh"),
           "CASE6_TEST_ROOT": str(test_root), "CASE6_TEST_EVENTS": str(events),
           "CASE6_REAL_PYTHON": "/data3/whn/Project2/OSWorld-V2/.venv/bin/python"}
    completed = subprocess.run(["bash", "-c", command], cwd=repo, env=env,
                               capture_output=True, text=True, timeout=15)
    assert completed.returncode == 0
    assert completed.stdout.strip().endswith("2 3")
    saved = json.loads((test_root / "runs/fixture-run/result.json").read_text())
    assert saved["status"] == "INVALID_INFRA_OR_RUNNER_ERROR"
    assert saved["pre_transport_status"] == "FAIL"
