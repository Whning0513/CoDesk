import base64
import json
import shlex
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

    def get_file(self, path):
        return self.files.get(path)

    def run_bash_script(self, script, timeout=30):
        if self.fail_transfer:
            return {"status": "error"}
        if script.startswith("if test -f "):
            path = shlex.split(script.split(";", 1)[0])[3]
            return {"status": "success", "output": "1" if path in self.files else "0"}
        lines = script.splitlines()
        if lines[-1].startswith("stat -c %a"):
            path = shlex.split(lines[-1])[-1]
            if lines[-2].startswith("chmod a-w"):
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
