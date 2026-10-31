"""Validate control and Pilot evidence before creating a formal freeze record."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from . import fixtures, oracle, resource_sampler, spec
from .private.gold import TAG_PATTERN
from oscombo.collab.workspace_assembly.fixtures import read_odt

CONTROL_SEED = "codesk-wa-v2-control-20261031"
PILOT_SEED = "codesk-wa-v2-pilot-20261031"
ROUND_SEEDS = {f"round{i}": f"codesk-wa-v2-round{i}-20261031" for i in (1, 2, 3)}
SEQUENCE = [("round1", "isolated"), ("round1", "shared"), ("round1", "shared_lock"),
            ("round2", "shared_lock"), ("round2", "shared"), ("round2", "isolated"),
            ("round3", "isolated"), ("round3", "shared_lock"), ("round3", "shared")]
SLOTS = {"positive_shared": ("shared", False, False), "positive_isolated": ("isolated", False, False),
         "negative_shared": ("shared", True, False), "negative_isolated": ("isolated", True, False),
         "probe_shared": ("shared", False, True), "probe_isolated": ("isolated", False, True)}


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def _file(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    _require(root.resolve() in target.parents and target.is_file(), f"missing/unsafe run evidence: {relative}")
    return target


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _common(root: Path, commit: str, seed: str, condition: str) -> tuple[dict, dict]:
    meta, result = _read(root / "provenance.json"), _read(root / "result.json")
    _require(meta.get("case_id") == spec.CASE_ID and meta.get("case_version") == spec.CASE_VERSION,
             f"{root.name}: wrong case/version")
    _require(meta.get("run_id") == root.name and meta.get("source_commit") == commit and meta.get("fixture_seed") == seed,
             f"{root.name}: run, source commit or seed mismatch")
    _require(meta.get("condition") == "collaborative_" + condition, f"{root.name}: wrong condition")
    _require(meta.get("guest_resources_requested") == {"cpus": "8", "ram": "8G"},
             f"{root.name}: resource request mismatch")
    resource = resource_sampler.summarize(root)
    _require(resource == _read(root / "resource_audit.json") and resource.get("valid") is True,
             f"{root.name}: actual QEMU resource audit missing/invalid")
    _require(result.get("postscore_lifecycle_ok") is True and result.get("reopen_complete") is True and
             result.get("bridge_valid") is True, f"{root.name}: reopen/bridge invalid")
    count = 1 if condition == "shared" else 2
    _require(len(result.get("reset", [])) == count and all(x.get("workspace_clean") is True for x in result["reset"]),
             f"{root.name}: reset evidence incomplete")
    sync = _read(root / "workspace_sync_result.json")
    _require(sync.get("final_sync_succeeded") is True and sync.get("verified") is True and
             sync.get("diagnostics", {}).get("infrastructure_review_required") is False,
             f"{root.name}: bridge history requires infrastructure review")
    with tempfile.TemporaryDirectory(prefix="codesk-wa-v2-freeze-") as temp:
        expected = fixtures.build_fixture(Path(temp) / "fixture", seed=seed)["fixture_sha256"]
    _require(_read(root / "fixtures/fixture_manifest.json").get("fixture_sha256") == expected,
             f"{root.name}: fixture differs from deterministic seed")
    for name, item in expected.items():
        _require(_sha(root / "fixtures" / name) == item["sha256"], f"{root.name}: fixture file hash mismatch")
    rescored = oracle.evaluate(root / "fixtures/inspection_note.txt",
        root / "artifacts/A/incoming/inspection_note.txt", root / "artifacts/A/inspection_note.txt",
        root / "fixtures/handoff_report.odt", root / "artifacts/B/handoff_report.odt")
    _require(rescored == _read(root / "oracle.json") == result.get("oracle"),
             f"{root.name}: independent artifact rescore mismatch")
    return meta, result


def _events(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        obj = json.loads(line)
        _require(isinstance(obj, dict), f"{path}: malformed event")
        rows.append(obj)
    return rows


def _control(root: Path, commit: str, name: str) -> dict:
    side, negative, probe = SLOTS[name]
    meta, result = _common(root, commit, CONTROL_SEED, side)
    _require(meta.get("model_called") is False and meta.get("scripted_negative_control") is negative and
             meta.get("scripted_view_version_probe") is probe, f"{root.name}: wrong control type")
    _require(result.get("status") == ("FAIL" if negative else "PASS"), f"{root.name}: unexpected control Oracle")
    score = result["oracle"]
    _require(score.get("actors", {}).get("A", {}).get("success") is True, f"{root.name}: A control did not deliver")
    checks = score.get("actors", {}).get("B", {}).get("checks", {})
    if negative:
        _require(checks.get("tag_matches_source") is False and
                 all(value is True for key, value in checks.items() if key != "tag_matches_source"),
                 f"{root.name}: negative did not isolate wrong tag")
    else:
        _require(score.get("joint_success") is True, f"{root.name}: positive did not pass")
    pre, view = _read(root / "control_prework.json"), _read(root / "control_B_peer_view.json")
    _require(_sha(_file(root, "control_prework.odt")) == pre.get("sha256"), f"{root.name}: prework SHA")
    pre_text, _ = read_odt(root / "control_prework.odt")
    draft, _ = read_odt(root / "fixtures/handoff_report.odt")
    audience = re.search(r"(?im)^Prepared for ([A-Za-z][A-Za-z -]+?) review\.$", draft)
    _require(audience is not None and bool(re.search(r"(?im)^(?:audience|for):\s*" +
             re.escape(audience.group(1)) + r"(?:\s+team)?[.!]?$", pre_text)),
             f"{root.name}: prework did not save the draft audience")
    _file(root, pre["trace_path"])
    _file(root, view["trace_path"])
    _file(root, view["screenshot"])
    _require(view.get("mode") == "444" and bool(int(view.get("owner_mode", "0"), 8) & 0o200) and
             "read-only" in view.get("window", "").casefold(), f"{root.name}: view/owner mode")
    _require(_sha(_file(root, view["recovered_copy"])) == view.get("sha256"), f"{root.name}: peer-view SHA")
    source = (root / "fixtures/inspection_note.txt").read_text(encoding="utf-8")
    match = re.search(TAG_PATTERN, source)
    _require(match is not None, f"{root.name}: source tag missing")
    tag = match.group(1).casefold()
    messages = [e for e in _events(root / "collaboration/events.jsonl")
                if e.get("type") == "message" and e.get("actor") == "A"]
    _require(bool(messages) and not any(tag in str(e.get("body", "")).casefold() for e in messages),
             f"{root.name}: control A message leaks tag or is missing")
    events = _events(root / "workspace_versions/events.jsonl")
    commits = [e for e in events if e.get("event") == "revision_committed" and e.get("actor") == "A"]
    _require(bool(commits) and pre["finished_at"] < commits[0]["time"] <= view["opened_at"],
             f"{root.name}: prework/handoff/read chronology")
    _require(any(commits[0]["time"] <= e.get("timestamp", 0) <= view["opened_at"] for e in messages),
             f"{root.name}: handoff message chronology")
    final_A = _read(root / "workspace_sync_result.json").get("final_versions", {}).get("A", {})
    _require(all(final_A.get(k) == view.get(k) for k in ("revision", "sha256", "peer_view_path")),
             f"{root.name}: GUI read did not use final delivered revision")
    _require(any(e.get("event") == "peer_view_verified" and e.get("actor") == "A" and
                 e.get("revision") == view["revision"] and e.get("sha256") == view["sha256"] and
                 e.get("mode") == "444" and e.get("time", 0) <= view["opened_at"] for e in events),
             f"{root.name}: matching peer view verification missing")
    if probe:
        data = _read(root / "control_view_revisions.json")
        views = data.get("views", [])
        _require(len(views) == 3 and views[0]["revision"] < views[1]["revision"] < views[2]["revision"] and
                 views[0]["sha256"] == views[2]["sha256"] != views[1]["sha256"],
                 f"{root.name}: revision probe sequence")
        for item in views:
            _require(item.get("mode") == "444" and _sha(_file(root, item["recovered_copy"])) == item["sha256"],
                     f"{root.name}: old/new revision recovered copy")
    return {"run_id": root.name, "status": result["status"], "source_commit": commit}


def _pilot(root: Path, commit: str, review_path: Path) -> dict:
    meta, result = _common(root, commit, PILOT_SEED, "isolated")
    _require(meta.get("model_called") is True and meta.get("model") == "gpt-6-astra" and
             meta.get("model_effort") == "medium" and meta.get("model_timeout") == 600 and
             meta.get("diagnostic_step_limit") == 12 and meta.get("actor_mcp_only") is True and
             meta.get("yield_wait_lifecycle") is True and result.get("status") in {"PASS", "FAIL"},
             f"{root.name}: Pilot config or status invalid")
    relay = _events(root / "codex_relay_events.jsonl")
    _require(bool(relay) and all(e.get("actor_mcp_only") is True and e.get("upstream_status") == 200 for e in relay),
             f"{root.name}: Pilot relay/allowlist failure")
    for role in "AB":
        path = _file(root, f"actor_runs/{role}/{role}/stdout.log")
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                item = event.get("item") or {}
                if event.get("type") == "item.started" and "call" in str(item.get("type", "")):
                    _require(item.get("type") == "mcp_tool_call" and item.get("server") in {"desktop", "collaboration"},
                             f"{root.name}: Actor used a tool outside the contract")
    _file(root, "behavioral_audit.json")
    metrics = _read(root / "model_metrics_v2.json")
    _require(not metrics.get("lifecycle_errors") and set(metrics.get("actors", {})) == {"A", "B"},
             f"{root.name}: Pilot timing or Actor metrics incomplete")
    review = _read(review_path)
    _require(review.get("run_id") == root.name and review.get("reviewed") is True and
             review.get("decision") == "proceed" and bool(str(review.get("reason", "")).strip()),
             f"{root.name}: explicit Pilot evidence review is missing")
    return {"run_id": root.name, "status": result["status"], "review": review}


def create(output: Path, controls: dict[str, Path], control_review: Path,
           pilot: Path, review: Path, image: Path) -> dict:
    _require(set(controls) == set(SLOTS), "six distinct control slots are required")
    roots = [p.resolve() for p in [*controls.values(), pilot]]
    _require(len(set(roots)) == 7 and len({p.name for p in roots}) == 7, "run IDs must be unique")
    subprocess.run(["git", "diff", "--quiet"], check=True)
    subprocess.run(["git", "diff", "--cached", "--quiet"], check=True)
    commit = subprocess.check_output(["git", "rev-parse", "--verify", "HEAD"], text=True).strip()
    control_results = {name: _control(Path(path).resolve(), commit, name) for name, path in controls.items()}
    visual = _read(control_review)
    _require(visual.get("reviewed") is True and bool(str(visual.get("reviewer", "")).strip()),
             "manual GUI control review is required")
    for item in control_results.values():
        details = visual.get("runs", {}).get(item["run_id"], {})
        _require(details.get("prework_screenshot_checked") is True and
                 details.get("readonly_view_screenshot_checked") is True,
                 f"{item['run_id']}: manual screenshot review is missing")
    pilot_result = _pilot(pilot.resolve(), commit, review)
    round_hashes = {}
    for round_name, seed in ROUND_SEEDS.items():
        with tempfile.TemporaryDirectory(prefix="codesk-wa-v2-round-") as temp:
            round_hashes[round_name] = fixtures.build_fixture(Path(temp) / "fixture", seed=seed)["fixture_sha256"]
    note_hashes = {row["inspection_note.txt"]["sha256"] for row in round_hashes.values()}
    _require(len(note_hashes) == 3, "formal round tags/notes are not distinct")
    image = image.resolve(strict=True)
    stat = image.stat()
    image_stat = {"bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    runtimes = set()
    for root in roots:
        meta = _read(root / "provenance.json")
        _require(meta.get("base_image_path") == str(image) and meta.get("base_image_stat") == image_stat,
                 f"{root.name}: Guest base image changed since its run")
        runtime = meta.get("runtime_image")
        _require(isinstance(runtime, str) and runtime.startswith("sha256:"),
                 f"{root.name}: runtime image must be pinned by image ID")
        runtimes.add(runtime)
        resources = _read(root / "ownership.json").get("resources", [])
        guests = [item for item in resources if item.get("kind") == "guest-container"]
        _require(len(guests) == meta.get("guest_count") and all(
            item.get("image_id") == runtime and item.get("labels", {}).get("oscombo.run") == root.name and
            item.get("base_mount", {}).get("Source") == str(image) and
            item.get("base_mount", {}).get("RW") is False for item in guests),
            f"{root.name}: runtime identity, run ownership or read-only base mount mismatch")
    _require(len(runtimes) == 1, "control and Pilot runtime images differ")
    image_sha = _sha(image)
    final_stat = image.stat()
    _require({"bytes": final_stat.st_size, "mtime_ns": final_stat.st_mtime_ns} == image_stat,
             "Guest base image changed while hashing")
    record = {"source_commit": commit, "case_id": spec.CASE_ID, "case_version": spec.CASE_VERSION,
              "model": "gpt-6-astra", "model_effort": "medium", "steps_per_role": 25,
              "active_seconds_per_role": 1200, "guest_cpus": 8, "guest_ram": "8G",
              "round_seeds": ROUND_SEEDS, "round_fixture_sha256": round_hashes,
              "formal_sequence": SEQUENCE, "controls_verified": True, "pilot_reviewed": True,
              "controls": control_results, "control_visual_review": visual, "pilot": pilot_result,
              "image_path": str(image), "image_sha256": image_sha,
              "image_stat": image_stat, "runtime_image": next(iter(runtimes))}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for slot in SLOTS:
        parser.add_argument("--" + slot.replace("_", "-"), type=Path, required=True)
    parser.add_argument("--control-review", type=Path, required=True)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--pilot-review", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = create(args.output, {slot: getattr(args, slot) for slot in SLOTS}, args.control_review,
                    args.pilot, args.pilot_review, args.image)
    print(json.dumps({"source_commit": result["source_commit"], "output": str(args.output)}))
