import json

from oscombo.collab.data_to_deck.live_pilot import _recorded_actor_status


def test_terminal_signal_only_reads_completed_peer_record(tmp_path):
    assert _recorded_actor_status(tmp_path, "A") is None
    path = tmp_path / "actors.jsonl"
    path.write_text('{partial\n' + json.dumps({"actor": "B", "status": "done"}) + "\n")
    assert _recorded_actor_status(tmp_path, "A") is None
    with path.open("a") as stream:
        stream.write(json.dumps({"actor": "A", "status": "done"}) + "\n")
    assert _recorded_actor_status(tmp_path, "A") == "done"
