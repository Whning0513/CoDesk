import fcntl
import json
from pathlib import Path

import pytest

from oscombo.collab.workspace_assembly_lite_v2 import deferred_cleanup as dc


class MissingContainer(Exception):
    pass


class Container:
    def __init__(self, cid, run):
        self.id = cid
        self.attrs = {"Config": {"Labels": {"oscombo": "1", "oscombo.run": run}}}
        self.removed = False
    def reload(self): pass
    def remove(self, *, force, v):
        assert force and not v
        self.removed = True


class Client:
    def __init__(self, containers):
        self.items = {c.id: c for c in containers}
        self.containers = self
    def get(self, cid):
        item = self.items[cid]
        if item.removed:
            raise MissingContainer("synthetic missing container")
        return item


def setup_run(tmp_path):
    root = tmp_path / "run"
    (root / "workspace_versions").mkdir(parents=True)
    (root / "workspace_versions/writer.lock").touch()
    a, b = "a" * 64, "b" * 64
    dc.write_pending(root, "run", {"A": a, "B": b}, "worker alive")
    ca, cb = Container(a, "run"), Container(b, "run")
    return root, ca, cb, Client([ca, cb])


def test_wait_for_coordinator_and_lease_before_removing(tmp_path):
    root, a, b, client = setup_run(tmp_path)
    with pytest.raises(RuntimeError, match="still alive"):
        dc.cleanup(root, client, pid_alive=lambda _: True, not_found=MissingContainer)
    assert not a.removed and not b.removed
    with (root / "workspace_versions/writer.lock").open("r+") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="lease remains"):
            dc.cleanup(root, client, pid_alive=lambda _: False, not_found=MissingContainer)
    assert not a.removed and not b.removed
    result = dc.cleanup(root, client, pid_alive=lambda _: False, not_found=MissingContainer)
    assert result["status"] == "complete" and a.removed and b.removed
    assert (root / "bridge_cleanup_supervisor.json").exists()


def test_wrong_ownership_never_removes_container(tmp_path):
    root, a, b, client = setup_run(tmp_path)
    a.attrs["Config"]["Labels"]["oscombo.run"] = "someone-else"
    with pytest.raises(RuntimeError, match="non-owned"):
        dc.cleanup(root, client, pid_alive=lambda _: False, not_found=MissingContainer)
    assert not a.removed and not b.removed
    (root / "workspace_versions/writer.lock").unlink()
    with pytest.raises(FileNotFoundError):
        dc.cleanup(root, client, pid_alive=lambda _: False, not_found=MissingContainer)


def test_pending_requires_full_ids_and_matching_root(tmp_path):
    root = tmp_path / "run"
    root.mkdir()
    with pytest.raises(ValueError):
        dc.write_pending(root, "run", {"A": "short"}, "error")
    with pytest.raises(ValueError):
        dc.write_pending(root, "different", {"A": "a" * 64}, "error")


def test_runner_defers_only_live_worker_and_marks_all_stop_errors(tmp_path):
    from oscombo.collab import lite_file_guest_pilot as runner
    root, a, b, client = setup_run(tmp_path)
    (root / "bridge_cleanup_pending.json").unlink()
    class Thread:
        alive = True
        def is_alive(self): return self.alive
    class Bridge:
        _thread = Thread()
        def stop(self): raise RuntimeError("stop failed")
    errors = []
    assert runner._stop_bridge_before_cleanup(Bridge(), "workspace_assembly_v2", root, "run",
        {"A": a.id, "B": b.id}, errors) is True
    assert errors and json.loads((root / "bridge_cleanup_pending.json").read_text())["guest_ids"]["A"] == a.id
    (root / "bridge_cleanup_pending.json").unlink()
    Bridge._thread.alive = False
    errors = []
    assert runner._stop_bridge_before_cleanup(Bridge(), "workspace_assembly_v2", root, "run",
        {"A": a.id, "B": b.id}, errors) is False
    assert errors and not (root / "bridge_cleanup_pending.json").exists()
