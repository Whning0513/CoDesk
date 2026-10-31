"""Finish run-owned Guest cleanup after a stuck bridge writer process exits.

Never removes overlays or containers without a matching full ID and run label.
The caller must have waited for the coordinator process before invoking this.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
from pathlib import Path


def write_pending(root: Path, run_id: str, ids: dict[str, str], error: str) -> None:
    if root.name != run_id or not ids or any(not re.fullmatch(r"[0-9a-f]{64}", cid or "") for cid in ids.values()):
        raise ValueError("invalid deferred cleanup ownership")
    pending = {"run_id": run_id, "coordinator_pid": os.getpid(), "guest_ids": ids,
               "reason": error, "status": "awaiting_coordinator_exit"}
    tmp = root / "bridge_cleanup_pending.json.tmp"
    tmp.write_text(json.dumps(pending, indent=2) + "\n")
    tmp.replace(root / "bridge_cleanup_pending.json")


def cleanup(root: Path, client, *, pid_alive=None, not_found=None) -> dict:
    if not_found is None:
        from docker.errors import NotFound
        not_found = NotFound
    root = root.resolve()
    pending_path = root / "bridge_cleanup_pending.json"
    pending = json.loads(pending_path.read_text())
    if (pending["run_id"] != root.name or type(pending.get("coordinator_pid")) is not int or
            pending["coordinator_pid"] <= 1):
        raise ValueError("invalid deferred cleanup run identity")
    ids = pending.get("guest_ids")
    if (not isinstance(ids, dict) or set(ids) not in ({"shared"}, {"A", "B"}) or
            len(set(ids.values())) != len(ids) or any(not isinstance(cid, str) or
            not re.fullmatch(r"[0-9a-f]{64}", cid) for cid in ids.values())):
        raise ValueError("invalid deferred cleanup container IDs")
    if pid_alive is None:
        def pid_alive(pid):
            try:
                os.kill(pid, 0)
                return True
            except ProcessLookupError:
                return False
            except PermissionError:
                return True
    if pid_alive(pending["coordinator_pid"]):
        raise RuntimeError("coordinator still alive; Guest cleanup deferred")
    lock_path = root / "workspace_versions" / "writer.lock"
    # Open existing lease only: a missing lock fails closed rather than inventing one.
    with lock_path.open("r+") as lease:
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("bridge writer lease remains held") from exc
        outcomes = []
        def record(event):
            with (root / "bridge_cleanup_events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, sort_keys=True) + "\n")
        for role, cid in ids.items():
            try:
                container = client.containers.get(cid)
            except Exception as exc:
                # Only Docker's explicit NotFound counts as already removed.
                if isinstance(exc, not_found):
                    event = {"role": role, "container_id": cid, "status": "already_missing"}
                    record(event)
                    outcomes.append(event)
                    continue
                raise
            container.reload()
            labels = container.attrs.get("Config", {}).get("Labels") or {}
            if container.id != cid or labels.get("oscombo") != "1" or labels.get("oscombo.run") != root.name:
                record({"role": role, "container_id": cid, "status": "ownership_mismatch"})
                raise RuntimeError(f"refusing non-owned container for role {role}")
            record({"role": role, "container_id": cid, "status": "remove_requested"})
            container.remove(force=True, v=False)
            try:
                client.containers.get(cid).reload()
            except not_found:
                pass
            else:
                record({"role": role, "container_id": cid, "status": "still_present"})
                raise RuntimeError(f"owned container remains after remove for role {role}")
            event = {"role": role, "container_id": cid, "status": "removed"}
            record(event)
            outcomes.append(event)
        result = {"run_id": root.name, "status": "complete", "guests": outcomes,
                  "scope": "exact owned containers only; overlays preserved"}
        (root / "bridge_cleanup_supervisor.json").write_text(json.dumps(result, indent=2) + "\n")
        return result


if __name__ == "__main__":
    import argparse
    import docker
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root", type=Path)
    args = parser.parse_args()
    client = docker.from_env(timeout=10)
    try:
        print(json.dumps(cleanup(args.run_root, client)))
    finally:
        client.close()
