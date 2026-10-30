"""Classify historical model runs without changing any run artifacts."""
from __future__ import annotations

import json
from pathlib import Path

from audit_actor_tool_boundary import audit


def classify(root: Path) -> list[dict]:
    rows = []
    for run in sorted(root.iterdir()):
        provenance = run / "provenance.json"
        if not provenance.exists():
            continue
        meta = json.loads(provenance.read_text())
        if not meta.get("model_called"):
            continue
        tools = audit(run)
        extra = {role: item["outside_gui_collaboration_contract"]
                 for role, item in tools["actors"].items()
                 if item["outside_gui_collaboration_contract"]}
        result = json.loads((run / "result.json").read_text()) if (run / "result.json").exists() else None
        oracle = json.loads((run / "oracle.json").read_text()) if (run / "oracle.json").exists() else None
        reopen = json.loads((run / "reopen_evidence.json").read_text()) if (run / "reopen_evidence.json").exists() else []
        reset = json.loads((run / "reset_evidence.json").read_text()) if (run / "reset_evidence.json").exists() else []
        if not reset and result:
            reset = result.get("reset", [])
        role_reopen = [item for item in reopen
                       if item.get("actor", item.get("role")) in ("A", "B")
                       and ("same_bytes" in item or "same_bytes_after_gui_reopen" in item)]
        reopen_ok = len(role_reopen) == 2 and all(
            item.get("same_bytes", item.get("same_bytes_after_gui_reopen")) is True
            and item.get("gui_reopen") != "skipped_unsaved_buffer"
            for item in role_reopen)
        complete = bool(result and oracle and reopen_ok and reset)
        rows.append({"run_id": run.name, "case_id": meta.get("case_id"),
                     "condition": meta.get("condition"),
                     "status": result.get("status") if result else "INVALID_INFRA",
                     "oracle_joint_success": oracle.get("joint_success") if oracle else None,
                     "complete_reopen_reset": complete,
                     "outside_contract_calls": extra,
                     "strict_comparable": complete and not extra})
    return rows


if __name__ == "__main__":
    out = Path("audits/three_lite_cases_20261029/historical_model_validity.json")
    out.write_text(json.dumps(classify(Path("runs")), indent=2) + "\n")
    print(out)
