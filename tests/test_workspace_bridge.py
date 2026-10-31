import base64
import json
import shlex
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from oscombo.collab.data_to_deck import spec
from oscombo.collab.data_to_deck.fixtures import build_fixture, _ods, authority_sheets
from oscombo.collab.data_to_deck.workspace_bridge import SavedArtifactBridge, digest
from oscombo.collab.data_to_deck.protocol import ProtocolStore, make_server
from oscombo.collab.data_to_deck.collab_tools import CollaborationClient


class Files:
    """In-memory controller double. No Guest or GUI success is claimed here."""
    def __init__(self, files):
        self.files = dict(files)
        self.modes = {path: "644" for path in files}
        self.fail_transfer = False
        self.fail_view = False

    def get_file(self, path):
        return self.files.get(path)

    def run_bash_script(self, script, timeout=30):
        if self.fail_transfer:
            return {"status": "error"}
        if script.startswith("if test -f "):
            path = shlex.split(script.split(";", 1)[0])[3]
            return {"status": "success", "output": "1" if path in self.files else "0"}
        lines = script.splitlines()
        if any(line.startswith("ln -- ") for line in lines):
            if self.fail_view:
                return {"status": "error", "returncode": 1}
            source_line = next(line for line in lines if "base64 -d >" in line)
            data = base64.b64decode(shlex.split(source_line)[2])
            destination = shlex.split(next(line for line in lines if line.startswith("ln -- ")))[-1]
            if destination in self.files:
                return {"status": "error", "returncode": 1}
            self.files[destination], self.modes[destination] = data, "444"
            return {"status": "success"}
        if lines[-1].startswith("stat -c %a"):
            path = shlex.split(lines[-1])[-1]
            if len(lines) > 1 and lines[-2].startswith("chmod a-w"):
                self.modes[path] = "444"
            return {"status": "success", "output": self.modes[path] + "\n"}
        source_line = next(line for line in lines if "base64 -d >" in line)
        data = base64.b64decode(shlex.split(source_line)[2])
        destination = shlex.split(lines[-1])[-1]
        self.files[destination] = data
        self.modes[destination] = "444" if any(line.startswith("chmod a-w") for line in lines) else "644"
        return {"status": "success"}


def setup_bridge(tmp_path, shared=False):
    fixture = tmp_path / "fixture"
    build_fixture(fixture)
    files = {f"/task/{spec.OUTPUTS[r]}": (fixture / spec.FIXTURE_NAMES[n]).read_bytes()
             for r, n in (("A", "authority"), ("B", "draft"))}
    a = Files(files)
    b = a if shared else Files(files)
    bridge = SavedArtifactBridge(tmp_path / "versions", "test", "/task", {"A": a, "B": b},
                                 {"A": "shared" if shared else "A", "B": "shared" if shared else "B"})
    bridge.sync()
    return bridge, a, b


def edited_workbook(tmp_path):
    sheets = authority_sheets()
    sheets["Reconciliation"].append(["progress", "note", "draft", "status", "public input"])
    path = tmp_path / "draft.ods"
    _ods(path, sheets)
    return path.read_bytes()


@pytest.mark.parametrize("shared", [False, True])
def test_saved_outputs_versioned_and_peer_reads_exact_bytes(tmp_path, shared):
    bridge, a, b = setup_bridge(tmp_path, shared)
    path = f"/task/{spec.OUTPUTS['A']}"
    initial = a.get_file(path)
    a.files[path] = edited_workbook(tmp_path)
    revision = bridge.publish("A")
    assert revision["revision"] == 1
    assert revision["sha256"] == digest(b.get_file(path))
    assert (bridge.root / "A/revision-000000.ods").read_bytes() == initial
    assert bridge.publish("A")["revision"] == 1  # no duplicate version for repeated publication
    ownership = json.loads((bridge.root / "ownership.json").read_text())
    assert ownership["writer_roles"][spec.OUTPUTS["A"]] == "A"
    assert set(bridge.snapshot()) == {"A", "B"}


def test_non_owner_change_is_preserved_and_rejected(tmp_path):
    bridge, a, b = setup_bridge(tmp_path)
    path = f"/task/{spec.OUTPUTS['A']}"
    b.files[path] = b"unexpected non-owner edit"
    a.files[path] = edited_workbook(tmp_path)
    with pytest.raises(RuntimeError, match="non-owner"):
        bridge.publish("A")
    assert b.files[path] == b"unexpected non-owner edit"
    assert bridge.snapshot()["A"]["revision"] == 0


def test_failed_transfer_can_retry_without_losing_revision(tmp_path):
    bridge, a, b = setup_bridge(tmp_path)
    path = f"/task/{spec.OUTPUTS['A']}"
    a.files[path] = edited_workbook(tmp_path)
    b.fail_transfer = True
    with pytest.raises(RuntimeError, match="transfer"):
        bridge.publish("A")
    b.fail_transfer = False
    assert bridge.publish("A")["revision"] == 1
    assert a.files[path] == b.files[path]


def test_lite_peer_outputs_are_read_only_before_actor_start_and_after_transfer(tmp_path):
    fixture = tmp_path / "fixture"
    build_fixture(fixture)
    files = {f"/task/{spec.OUTPUTS[r]}": (fixture / spec.FIXTURE_NAMES[n]).read_bytes()
             for r, n in (("A", "authority"), ("B", "draft"))}
    a, b = Files(files), Files(files)
    bridge = SavedArtifactBridge(tmp_path / "versions", "lite", "/task", {"A": a, "B": b},
                                 {"A": "A", "B": "B"}, peer_read_only=True)
    bridge.start()
    try:
        a_path, b_path = (f"/task/{spec.OUTPUTS[r]}" for r in "AB")
        assert a.modes[a_path] == b.modes[b_path] == "644"
        assert b.modes[a_path] == a.modes[b_path] == "444"
        a.files[a_path] = edited_workbook(tmp_path)
        revision = bridge.publish("A")
        assert revision["revision"] == 1
        assert b.files[a_path] == a.files[a_path]
        assert b.modes[a_path] == "444"
    finally:
        bridge.stop()


def test_partial_save_and_wrong_type_are_not_transferred(tmp_path):
    bridge, a, b = setup_bridge(tmp_path)
    path = f"/task/{spec.OUTPUTS['A']}"
    initial = b.files[path]
    a.files[path] = b"unfinished zip save"
    with pytest.raises(Exception):
        bridge.publish("A")
    assert b.files[path] == initial
    a.files[path] = a.files[f"/task/{spec.OUTPUTS['B']}"]
    with pytest.raises(RuntimeError, match="document type"):
        bridge.publish("A")
    with pytest.raises(ValueError, match="owned"):
        bridge.publish("../../oracle")


def test_http_publication_bound_to_authenticated_role(tmp_path):
    bridge, a, b = setup_bridge(tmp_path)
    server = make_server(ProtocolStore(tmp_path / "messages", "test"), {"A": "a", "B": "b"})
    server.workspace_bridge = bridge
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = CollaborationClient(f"http://127.0.0.1:{server.server_port}", "A", "a")
    try:
        assert client.publish_saved_artifact()["actor"] == "A"
        assert set(client.list_saved_artifacts()) == {"A", "B"}
        with pytest.raises(RuntimeError, match="400"):
            client._request("/artifacts/publish", "POST", {"actor": "B", "path": "/private/gold"})
        assert not (bridge.root / "private").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_case_specific_dual_workbook_outputs_preserve_role_ownership(tmp_path):
    fixture = tmp_path / "fixture"
    build_fixture(fixture)
    initial = (fixture / spec.FIXTURE_NAMES["authority"]).read_bytes()
    outputs = {"A": "outputs/forecast.ods", "B": "outputs/order.ods"}
    files = {f"/task/{path}": initial for path in outputs.values()}
    a, b = Files(files), Files(files)
    mime = "application/vnd.oasis.opendocument.spreadsheet"
    bridge = SavedArtifactBridge(tmp_path / "versions", "workbook-case", "/task",
                                 {"A": a, "B": b}, {"A": "A", "B": "B"},
                                 outputs=outputs, mime_types={"A": mime, "B": mime},
                                 peer_read_only=True)
    bridge.start()
    try:
        b.files["/task/outputs/order.ods"] = edited_workbook(tmp_path)
        revision = bridge.publish("B")
        assert revision["revision"] == 1
        assert a.files["/task/outputs/order.ods"] == b.files["/task/outputs/order.ods"]
        assert a.modes["/task/outputs/order.ods"] == "444"
        ownership = json.loads((bridge.root / "ownership.json").read_text())
        assert ownership["writer_roles"]["outputs/order.ods"] == "B"
    finally:
        bridge.stop()


def test_text_output_contract_rejects_non_utf8_and_syncs_saved_source(tmp_path):
    fixture = tmp_path / "fixture"
    build_fixture(fixture)
    ods = (fixture / spec.FIXTURE_NAMES["authority"]).read_bytes()
    outputs = {"A": "outputs/app.js", "B": "outputs/qa.ods"}
    files = {"/task/outputs/app.js": b"const ready = false;\n",
             "/task/outputs/qa.ods": ods}
    a, b = Files(files), Files(files)
    bridge = SavedArtifactBridge(tmp_path / "versions", "code-case", "/task",
                                 {"A": a, "B": b}, {"A": "A", "B": "B"},
                                 outputs=outputs,
                                 mime_types={"A": None, "B": "application/vnd.oasis.opendocument.spreadsheet"})
    bridge.sync()
    a.files["/task/outputs/app.js"] = b"\xff"
    with pytest.raises(UnicodeDecodeError):
        bridge.publish("A")
    assert b.files["/task/outputs/app.js"] == b"const ready = false;\n"
    a.files["/task/outputs/app.js"] = b"const ready = true;\n"
    assert bridge.publish("A")["revision"] == 1
    assert b.files["/task/outputs/app.js"] == a.files["/task/outputs/app.js"]


def test_blender_binary_revision_is_synced_without_text_decoding(tmp_path):
    outputs = {"A": "outputs/scene.blend", "B": "outputs/review.txt"}
    scene_path = "/task/outputs/scene.blend"
    initial = b"BLENDER" + b"\x00\xffinitial"
    edited = b"BLENDER" + b"\x00\xffedited"
    files = {scene_path: initial, "/task/outputs/review.txt": b"Pending\n"}
    a, b = Files(files), Files(files)
    bridge = SavedArtifactBridge(tmp_path / "versions", "blender-case", "/task",
                                 {"A": a, "B": b}, {"A": "A", "B": "B"},
                                 outputs=outputs,
                                 mime_types={"A": "application/x-blender", "B": None},
                                 peer_read_only=True)
    bridge.sync()
    a.files[scene_path] = b"not a Blender file"
    with pytest.raises(RuntimeError, match="Blender project"):
        bridge.publish("A")
    a.files[scene_path] = edited
    assert bridge.publish("A")["revision"] == 1
    assert b.files[scene_path] == edited
    assert b.modes[scene_path] == "444"


def test_compressed_blender_partial_frame_is_rejected_before_sync(tmp_path):
    fixture = (Path(__file__).resolve().parents[1] /
               "oscombo/collab/model_and_review_lite_v1/fixtures/Lamp_Review.blend").read_bytes()
    outputs = {"A": "outputs/scene.blend", "B": "outputs/review.txt"}
    scene_path = "/task/outputs/scene.blend"
    files = {scene_path: b"BLENDERinitial", "/task/outputs/review.txt": b"Pending\n"}
    a, b = Files(files), Files(files)
    bridge = SavedArtifactBridge(tmp_path / "versions", "blender-zstd", "/task",
                                 {"A": a, "B": b}, {"A": "A", "B": "B"},
                                 outputs=outputs,
                                 mime_types={"A": "application/x-blender", "B": None})
    bridge.sync()
    a.files[scene_path] = fixture[:100]
    with pytest.raises(RuntimeError, match="incomplete Zstd frame"):
        bridge.publish("A")
    assert b.files[scene_path] == b"BLENDERinitial"
    a.files[scene_path] = fixture
    assert bridge.publish("A")["revision"] == 1
    assert b.files[scene_path] == fixture


def test_new_file_is_published_only_after_owner_creates_it(tmp_path):
    fixture = tmp_path / "fixture"
    build_fixture(fixture)
    outputs = {"A": "outputs/agent_A/note.txt", "B": "outputs/agent_B/report.odp"}
    b_path = f"/task/{outputs['B']}"
    a_path = f"/task/{outputs['A']}"
    draft = (fixture / spec.FIXTURE_NAMES["draft"]).read_bytes()
    a, b = Files({b_path: draft}), Files({b_path: draft})
    bridge = SavedArtifactBridge(tmp_path / "versions", "new-file", "/task",
                                 {"A": a, "B": b}, {"A": "A", "B": "B"},
                                 outputs=outputs,
                                 mime_types={"A": None, "B": "application/vnd.oasis.opendocument.presentation"},
                                 allow_initial_missing={"A"}, peer_read_only=True)
    bridge.start()
    try:
        assert set(bridge.snapshot()) == {"B"}
        with pytest.raises(RuntimeError, match="no saved artifact"):
            bridge.publish("A")
        a.files[a_path] = b"inspection tag: RIVER-27\n"
        revision = bridge.publish("A")
        assert revision["revision"] == 1
        assert b.files[a_path] == a.files[a_path]
        assert b.modes[a_path] == "444"
    finally:
        bridge.stop()


def test_public_snapshot_does_not_wait_for_slow_guest_io_lock(tmp_path):
    bridge, _, _ = setup_bridge(tmp_path)
    observed = []
    with bridge._lock:
        reader = threading.Thread(target=lambda: observed.append(bridge.snapshot()), daemon=True)
        reader.start()
        reader.join(timeout=0.5)
        assert not reader.is_alive(), "public handoff snapshot blocked behind Guest I/O"
    assert set(observed[0]) == {"A", "B"}
    assert observed[0]["A"]["revision"] == 0


def make_view_bridge(tmp_path, shared=False, missing=False, resume=False):
    outputs = {"A": "outputs/agent_A/note.txt", "B": "outputs/agent_B/report.txt"}
    a_path, b_path = (f"/task/{outputs[r]}" for r in "AB")
    seed = {b_path: b"initial report\n"}
    if not missing:
        seed[a_path] = b"first note\n"
    a = Files(seed)
    b = a if shared else Files(seed)
    opts = dict(outputs=outputs, mime_types={"A": None, "B": None}, peer_read_only=True,
                peer_view_dirs={"A": "views/B"},
                allow_initial_missing={"A"} if missing else None)
    bridge = SavedArtifactBridge(tmp_path / "versions", "views", "/task", {"A": a, "B": b},
                                 {"A": "shared" if shared else "A",
                                  "B": "shared" if shared else "B"}, resume=resume, **opts)
    return bridge, a, b, opts


@pytest.mark.parametrize("shared", [False, True])
def test_immutable_peer_view_seed_and_later_revision(tmp_path, shared):
    bridge, a, b, _ = make_view_bridge(tmp_path, shared)
    a_path = "/task/outputs/agent_A/note.txt"
    first = bridge.publish("A")
    assert first["revision"] == 0
    assert first["peer_view_path"] == "views/B/note-r000000.txt"
    view0 = "/task/" + first["peer_view_path"]
    assert b.files[view0] == b"first note\n" and b.modes[view0] == "444"
    assert a.modes[a_path] == "644"
    a.files[a_path] = b"second note\n"
    second = bridge.publish("A")
    view1 = "/task/" + second["peer_view_path"]
    assert second["revision"] == 1 and b.files[view1] == b"second note\n"
    assert b.modes[view1] == "444" and b.files[view0] == b"first note\n"
    assert bridge.snapshot()["A"]["peer_view_path"] == second["peer_view_path"]
    assert bridge.publish("A") == second
    with pytest.raises(ValueError, match="owned"):
        bridge.publish("../A")


@pytest.mark.parametrize("shared", [False, True])
def test_missing_seed_first_published_view_is_revision_one(tmp_path, shared):
    bridge, a, b, _ = make_view_bridge(tmp_path, shared, missing=True)
    bridge.sync()
    assert "A" not in bridge.snapshot()
    a.files["/task/outputs/agent_A/note.txt"] = b"delivered\n"
    first = bridge.publish("A")
    assert first["revision"] == 1
    assert b.files["/task/views/B/note-r000001.txt"] == b"delivered\n"


@pytest.mark.parametrize("shared", [False, True])
def test_failed_view_is_not_published_and_retry_keeps_old_revision(tmp_path, shared):
    bridge, a, b, _ = make_view_bridge(tmp_path, shared)
    first = bridge.publish("A")
    a.files["/task/outputs/agent_A/note.txt"] = b"new revision\n"
    b.fail_view = True
    with pytest.raises(RuntimeError, match="view transfer failed"):
        bridge.publish("A")
    assert bridge.snapshot()["A"] == first
    # A concurrent B publication must not expose an uncommitted A revision.
    b.fail_view = False
    bridge.publish("B")
    assert bridge.snapshot()["A"] == first
    second = bridge.publish("A")
    assert second["revision"] == 1
    assert b.files["/task/views/B/note-r000000.txt"] == b"first note\n"
    assert b.files["/task/views/B/note-r000001.txt"] == b"new revision\n"


@pytest.mark.parametrize("shared", [False, True])
@pytest.mark.parametrize("corruption", ["bytes", "mode"])
def test_view_conflict_is_never_overwritten(tmp_path, shared, corruption):
    bridge, _, b, _ = make_view_bridge(tmp_path, shared=shared)
    path = "/task/views/B/note-r000000.txt"
    b.files[path] = b"unexpected" if corruption == "bytes" else b"first note\n"
    b.modes[path] = "444" if corruption == "bytes" else "644"
    original = (b.files[path], b.modes[path])
    with pytest.raises(RuntimeError, match="view conflict"):
        bridge.publish("A")
    assert (b.files[path], b.modes[path]) == original and bridge.snapshot() == {}


@pytest.mark.parametrize("shared", [False, True])
def test_published_view_tampering_revokes_delivery_until_reverified(tmp_path, shared):
    bridge, a, b, opts = make_view_bridge(tmp_path, shared=shared)
    first = bridge.publish("A")
    path = "/task/" + first["peer_view_path"]
    b.files[path] = b"tampered\n"
    with pytest.raises(RuntimeError, match="view conflict"):
        bridge.publish("A")
    assert bridge.snapshot()["A"]["delivered"] is False
    assert b.files[path] == b"tampered\n"
    bridge.close()
    restored = SavedArtifactBridge(bridge.root, "views", "/task", {"A": a, "B": b},
                                   bridge.guest_ids, resume=True, **opts)
    assert restored.snapshot()["A"]["delivered"] is False
    b.files[path] = b"first note\n"
    assert restored.publish("A")["delivered"] is True
    assert restored.snapshot()["A"].get("peer_view_invalidated") is None
    restored.close()


@pytest.mark.parametrize("bad", ["../escape", "/absolute", ".", "outputs", "outputs/agent_A/note.txt"])
def test_view_path_rejects_escape_and_ownership_overlap(tmp_path, bad):
    a = Files({})
    with pytest.raises(ValueError, match="peer view"):
        SavedArtifactBridge(tmp_path / "versions", "v", "/task", {"A": a, "B": a},
                            {"A": "shared", "B": "shared"}, peer_view_dirs={"A": bad},
                            outputs={"A": "outputs/agent_A/note.txt", "B": "outputs/agent_B/report.txt"})


@pytest.mark.parametrize("shared", [False, True])
def test_interrupted_after_view_can_resume_without_overwriting(tmp_path, monkeypatch, shared):
    bridge, a, b, opts = make_view_bridge(tmp_path, shared)
    first = bridge.publish("A")
    a.files["/task/outputs/agent_A/note.txt"] = b"new revision\n"
    original = bridge._ensure_peer_view
    def interrupted(*args):
        original(*args)
        raise RuntimeError("interrupted after immutable link")
    monkeypatch.setattr(bridge, "_ensure_peer_view", interrupted)
    with pytest.raises(RuntimeError, match="interrupted"):
        bridge.publish("A")
    assert bridge.snapshot()["A"] == first
    bridge.close()
    resumed = SavedArtifactBridge(bridge.root, "views", "/task", {"A": a, "B": b},
        bridge.guest_ids, resume=True, **opts)
    second = resumed.publish("A")
    assert second["revision"] == 1 and second["peer_view_path"] == "views/B/note-r000001.txt"
    assert b.files["/task/views/B/note-r000001.txt"] == b"new revision\n"
    resumed.close()
    with pytest.raises(ValueError, match="different ownership"):
        SavedArtifactBridge(bridge.root, "other", "/task", {"A": a, "B": b},
                            bridge.guest_ids, resume=True, **opts)


@pytest.mark.parametrize("shared", [False, True])
def test_simultaneous_publishers_commit_one_revision(tmp_path, shared):
    bridge, a, b, _ = make_view_bridge(tmp_path, shared=shared)
    bridge.publish("A")
    a.files["/task/outputs/agent_A/note.txt"] = b"concurrent\n"
    barrier = threading.Barrier(8)
    revisions, errors = [], []
    def worker():
        try:
            barrier.wait(timeout=5)
            revisions.append(bridge.publish("A"))
        except Exception as exc:
            errors.append(exc)
    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads: t.start()
    for t in threads: t.join(timeout=10)
    assert not errors and len(revisions) == 8
    assert {r["revision"] for r in revisions} == {1}
    assert b.files["/task/views/B/note-r000001.txt"] == b"concurrent\n"


class LocalMappedGuest:
    """Execute bridge shell against real files in one simulated Guest root."""
    def __init__(self, root):
        self.root = root

    def get_file(self, path):
        assert path.startswith("/task/")
        try:
            return (self.root / path.removeprefix("/task/")).read_bytes()
        except FileNotFoundError:
            return None

    def run_bash_script(self, script, timeout=30):
        script = script.replace("/task/", str(self.root) + "/")
        result = subprocess.run(["bash", "-c", script], capture_output=True,
                                text=True, timeout=timeout)
        return {"status": "success" if result.returncode == 0 else "error",
                "returncode": result.returncode, "output": result.stdout}


def test_real_filesystem_pending_copy_then_new_save_and_restart(tmp_path, monkeypatch):
    a, b = LocalMappedGuest(tmp_path / "a"), LocalMappedGuest(tmp_path / "b")
    for guest in (a, b):
        for directory in ("outputs/agent_A", "outputs/agent_B", "views/B"):
            (guest.root / directory).mkdir(parents=True)
        (guest.root / "outputs/agent_A/note.txt").write_bytes(b"A0\n")
        (guest.root / "outputs/agent_B/report.txt").write_bytes(b"draft\n")
    opts = dict(outputs={"A": "outputs/agent_A/note.txt", "B": "outputs/agent_B/report.txt"},
                mime_types={"A": None, "B": None}, peer_read_only=True,
                peer_view_dirs={"A": "views/B"})
    bridge = SavedArtifactBridge(tmp_path / "versions", "real", "/task", {"A": a, "B": b},
                                 {"A": "A", "B": "B"}, **opts)
    first = bridge.publish("A")
    (a.root / "outputs/agent_A/note.txt").write_bytes(b"A1\n")
    monkeypatch.setattr(bridge, "_ensure_peer_view", lambda *args: (_ for _ in ()).throw(RuntimeError("injected view failure")))
    with pytest.raises(RuntimeError, match="injected view failure"):
        bridge.publish("A")
    assert bridge.snapshot()["A"] == first
    assert (b.root / "outputs/agent_A/note.txt").read_bytes() == b"A1\n"
    assert (bridge.root / "A/revision-000001.txt").read_bytes() == b"A1\n"
    (a.root / "outputs/agent_A/note.txt").write_bytes(b"A2\n")
    bridge.close()
    resumed = SavedArtifactBridge(bridge.root, "real", "/task", {"A": a, "B": b},
                                  {"A": "A", "B": "B"}, resume=True, **opts)
    peer = b.root / "outputs/agent_A/note.txt"
    peer.chmod(0o644)
    peer.write_bytes(b"non-owner edit\n")
    with pytest.raises(RuntimeError, match="non-owner"):
        resumed.publish("A")
    peer.write_bytes(b"A1\n")
    peer.chmod(0o444)
    final = resumed.publish("A")
    assert final["revision"] == 2 and final["delivered"] is True
    assert (b.root / final["peer_view_path"]).read_bytes() == b"A2\n"
    assert (b.root / final["peer_view_path"]).stat().st_mode & 0o777 == 0o444
    assert (b.root / first["peer_view_path"]).read_bytes() == b"A0\n"
    assert (a.root / "outputs/agent_A/note.txt").stat().st_mode & 0o200
    events = [json.loads(line) for line in (bridge.root / "events.jsonl").read_text().splitlines()]
    assert any(e["event"] == "peer_view_error" and e["revision"] == 1 for e in events)
    assert any(e["event"] == "ownership_or_sync_conflict" for e in events)
    resumed.close()


def test_missing_view_parent_fails_closed_and_can_retry(tmp_path):
    guest = LocalMappedGuest(tmp_path / "guest")
    for directory in ("outputs/agent_A", "outputs/agent_B"):
        (guest.root / directory).mkdir(parents=True)
    (guest.root / "outputs/agent_A/note.txt").write_bytes(b"note\n")
    (guest.root / "outputs/agent_B/report.txt").write_bytes(b"draft\n")
    bridge = SavedArtifactBridge(tmp_path / "versions", "missing", "/task",
        {"A": guest, "B": guest}, {"A": "shared", "B": "shared"},
        outputs={"A": "outputs/agent_A/note.txt", "B": "outputs/agent_B/report.txt"},
        mime_types={"A": None, "B": None}, peer_read_only=True, peer_view_dirs={"A": "views/B"})
    with pytest.raises(RuntimeError, match="view transfer failed"):
        bridge.publish("A")
    assert bridge.snapshot() == {}
    assert '"event": "peer_view_error"' in (bridge.root / "events.jsonl").read_text()
    (guest.root / "views/B").mkdir(parents=True)
    assert bridge.publish("A")["revision"] == 0
    bridge.close()


def test_real_filesystem_view_handles_quoted_paths(tmp_path):
    class LocalGuest:
        def get_file(self, path):
            try:
                return Path(path).read_bytes()
            except FileNotFoundError:
                return None
        def run_bash_script(self, script, timeout=30):
            result = subprocess.run(["bash", "-c", script], capture_output=True,
                                    text=True, timeout=timeout)
            return {"status": "success" if result.returncode == 0 else "error",
                    "returncode": result.returncode, "output": result.stdout}
    task = tmp_path / "task ' with spaces"
    a_path, b_path = task / "outputs/agent_A/note.txt", task / "outputs/agent_B/report.txt"
    for directory in (a_path.parent, b_path.parent, task / "views/B"):
        directory.mkdir(parents=True)
    a_path.write_bytes(b"note\n")
    b_path.write_bytes(b"report\n")
    guest = LocalGuest()
    bridge = SavedArtifactBridge(tmp_path / "versions", "quoted", str(task),
        {"A": guest, "B": guest}, {"A": "shared", "B": "shared"},
        outputs={"A": "outputs/agent_A/note.txt", "B": "outputs/agent_B/report.txt"},
        mime_types={"A": None, "B": None}, peer_read_only=True, peer_view_dirs={"A": "views/B"})
    result = bridge.publish("A")
    view = task / result["peer_view_path"]
    assert view.read_bytes() == b"note\n" and view.stat().st_mode & 0o777 == 0o444
    assert not list((task / "views/B").glob("*.codesk-view-*"))
    bridge.close()


def test_writer_lease_excludes_another_process_until_exit(tmp_path):
    bridge, a, b, opts = make_view_bridge(tmp_path, shared=True)
    bridge.publish("A")
    bridge.close()
    code = '''import sys
from pathlib import Path
from oscombo.collab.data_to_deck.workspace_bridge import SavedArtifactBridge
class Dummy: pass
o={"A":"outputs/agent_A/note.txt","B":"outputs/agent_B/report.txt"}
b=SavedArtifactBridge(Path(sys.argv[1]), "views", "/task", {"A":Dummy(),"B":Dummy()},
 {"A":"shared","B":"shared"}, outputs=o, mime_types={"A":None,"B":None},
 peer_read_only=True, peer_view_dirs={"A":"views/B"}, resume=True)
print("locked", flush=True)
sys.stdin.readline()
'''
    proc = subprocess.Popen([sys.executable, "-c", code, str(bridge.root)],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "locked"
        with pytest.raises(RuntimeError, match="live writer"):
            SavedArtifactBridge(bridge.root, "views", "/task", {"A": a, "B": b},
                                bridge.guest_ids, resume=True, **opts)
    finally:
        # Abrupt death simulates an interrupted coordinator; the OS releases
        # its lock without requiring a cooperative close.
        proc.kill()
        proc.wait(timeout=10)
    resumed = SavedArtifactBridge(bridge.root, "views", "/task", {"A": a, "B": b},
                                  bridge.guest_ids, resume=True, **opts)
    assert resumed.snapshot()["A"]["revision"] == 0
    resumed.close()


def test_lease_released_on_failed_resume_and_failed_final_sync(tmp_path, monkeypatch):
    bridge, a, b, opts = make_view_bridge(tmp_path, shared=True)
    bridge.publish("A")
    bridge.close()
    with pytest.raises(ValueError, match="different ownership"):
        SavedArtifactBridge(bridge.root, "wrong", "/task", {"A": a, "B": b},
                            bridge.guest_ids, resume=True, **opts)
    restored = SavedArtifactBridge(bridge.root, "views", "/task", {"A": a, "B": b},
                                   bridge.guest_ids, resume=True, **opts)
    monkeypatch.setattr(restored, "sync", lambda: (_ for _ in ()).throw(RuntimeError("sync failed")))
    with pytest.raises(RuntimeError, match="sync failed"):
        restored.stop()
    again = SavedArtifactBridge(bridge.root, "views", "/task", {"A": a, "B": b},
                                bridge.guest_ids, resume=True, **opts)
    again.close()


def test_live_worker_keeps_lease_until_exited(tmp_path):
    bridge, a, b, opts = make_view_bridge(tmp_path, shared=True)
    finished = threading.Event()
    thread = threading.Thread(target=lambda: finished.wait(timeout=10))
    bridge._thread = thread
    thread.start()
    try:
        with pytest.raises(RuntimeError, match="worker is running"):
            bridge.close()
        with pytest.raises(RuntimeError, match="live writer"):
            SavedArtifactBridge(bridge.root, "views", "/task", {"A": a, "B": b},
                                bridge.guest_ids, resume=True, **opts)
    finally:
        finished.set()
        thread.join(timeout=5)
        bridge.close()


def test_failed_ownership_write_does_not_leak_lease(tmp_path, monkeypatch):
    import fcntl
    original = Path.write_text
    def fail_ownership(path, *args, **kwargs):
        if path.name == "ownership.json":
            raise OSError("injected ownership write failure")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "write_text", fail_ownership)
    a = Files({})
    root = tmp_path / "versions"
    with pytest.raises(OSError, match="ownership write failure"):
        SavedArtifactBridge(root, "v", "/task", {"A": a, "B": a},
            {"A": "shared", "B": "shared"}, peer_view_dirs={"A": "views/B"})
    with (root / "writer.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(handle, fcntl.LOCK_UN)
