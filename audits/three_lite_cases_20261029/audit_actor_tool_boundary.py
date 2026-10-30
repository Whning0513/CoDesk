"""Read-only audit of Codex CLI tool calls outside the GUI collaboration contract."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path


ALLOWED = {
    "screenshot", "click", "drag", "move", "type_text", "key", "scroll", "wait",
    "declare_infeasible", "send_message", "read_messages", "send_attachment",
    "read_attachment", "publish_saved_artifact", "list_saved_artifacts",
}


def audit(run_root: Path) -> dict:
    result = {"run_id": run_root.name, "actors": {}}
    for role in "AB":
        root = run_root / "actor_runs" / role / role / "codex_home/sessions"
        calls: Counter[str] = Counter()
        for path in root.rglob("*.jsonl"):
            for line in path.read_text().splitlines():
                record = json.loads(line)
                if record.get("type") != "response_item":
                    continue
                item = record.get("payload") or {}
                if item.get("type") in {"function_call", "custom_tool_call"}:
                    calls[item.get("name", "<unnamed>")] += 1
        result["actors"][role] = {
            "total_tool_calls": sum(calls.values()),
            "outside_gui_collaboration_contract": {
                name: count for name, count in sorted(calls.items()) if name not in ALLOWED
            },
        }
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.run_root), indent=2))
