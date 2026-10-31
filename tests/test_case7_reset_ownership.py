"""Fault injection for exact-ID cleanup after partial Guest reset."""
from types import SimpleNamespace
import pytest
from oscombo.collab import lite_file_guest_pilot as runner
from oscombo.collab.workspace_assembly_lite_v2 import deferred_cleanup as dc

OLD, NEW, OTHER = 'a' * 64, 'b' * 64, 'c' * 64


class Container:
    def __init__(self, cid, labels, store):
        self.id = cid
        self.labels = labels
        self.store = store
    def remove(self, *, force, v):
        assert force is True and v is False
        self.store.pop(self.id)


class Env:
    def __init__(self, cid, store):
        self.provider = SimpleNamespace(container=SimpleNamespace(id=cid) if cid else None)
        self.store = store
        self.close_count = 0
    def close(self):
        self.close_count += 1
        self.store.pop(self.provider.container.id)
        self.provider.container = None


def install_fake_docker(monkeypatch, store):
    monkeypatch.setattr(runner.core, '_missing_container', lambda cid: cid not in store)
    def verify(cid, run_id):
        obj = store[cid]
        if obj.id != cid or obj.labels != {'oscombo': '1', 'oscombo.run': run_id}:
            raise RuntimeError('ownership mismatch')
        return obj
    monkeypatch.setattr(runner.core, '_verify_container', verify)


def test_failed_reset_switches_id_and_cleans_only_exact_owned(monkeypatch):
    store = {}
    for cid, run in [(NEW, 'our-run'), (OTHER, 'other-run')]:
        store[cid] = Container(cid, {'oscombo': '1', 'oscombo.run': run}, store)
    env = Env(OLD, store)
    def failed_reset():
        env.provider.container = SimpleNamespace(id=NEW)
        raise TimeoutError('new Guest readiness timed out')
    install_fake_docker(monkeypatch, store)
    with pytest.raises(TimeoutError):
        try:
            failed_reset()
        finally:
            ids = runner._cleanup_candidates({'A': env}, {'A': OLD}, {'A'})
    assert ids == {'A': NEW, 'A:previous': OLD}
    runner._cleanup_exact_guest('A', env, ids, 'our-run')
    assert env.close_count == 1 and list(store) == [OTHER]


def test_new_foreign_id_cannot_be_closed_even_if_old_owned(monkeypatch):
    store = {}
    for cid, run in [(OLD, 'our-run'), (NEW, 'other-run')]:
        store[cid] = Container(cid, {'oscombo': '1', 'oscombo.run': run}, store)
    env = Env(NEW, store)
    install_fake_docker(monkeypatch, store)
    ids = runner._cleanup_candidates({'A': env}, {'A': OLD}, {'A'})
    with pytest.raises(RuntimeError, match='ownership mismatch'):
        runner._cleanup_exact_guest('A', env, ids, 'our-run')
    assert env.close_count == 0 and set(store) == {OLD, NEW}


def test_both_known_owned_ids_are_checked_and_removed(monkeypatch):
    store = {}
    for cid in (OLD, NEW):
        store[cid] = Container(cid, {'oscombo': '1', 'oscombo.run': 'our-run'}, store)
    env = Env(NEW, store)
    install_fake_docker(monkeypatch, store)
    ids = runner._cleanup_candidates({'A': env}, {'A': OLD}, {'A'})
    runner._cleanup_exact_guest('A', env, ids, 'our-run')
    assert env.close_count == 1 and not store


def test_unknown_reset_identity_is_preserved():
    env = Env(None, {})
    with pytest.raises(RuntimeError, match='identity is unavailable'):
        runner._cleanup_candidates({'A': env}, {'A': OLD}, {'A'})


def test_deferred_cleanup_schema_retains_both_ids():
    assert dc._valid_ids({'A': NEW, 'A:previous': OLD, 'B': OTHER})
    assert not dc._valid_ids({'A': NEW, 'A:previous': OLD, 'B': OTHER, 'unrelated': 'd'*64})
    assert not dc._valid_ids({'A': NEW, 'B': OTHER, 'A:previous': NEW})


def test_live_bridge_defers_both_reset_ids_and_no_guest_is_closed(tmp_path):
    import json
    root = tmp_path / 'our-run'
    root.mkdir()
    class Thread:
        def is_alive(self): return True
    class Bridge:
        _thread = Thread()
        def stop(self): raise RuntimeError('still alive')
    store = {NEW: object(), OLD: object(), OTHER: object()}
    a = Env(NEW, store)
    b = Env(OTHER, store)
    ids = runner._cleanup_candidates({'A': a, 'B': b}, {'A': OLD, 'B': OTHER}, {'A'})
    errors = []
    defer = runner._stop_bridge_before_cleanup(Bridge(), 'workspace_assembly_v2', root, 'our-run', ids, errors)
    assert defer is True and errors
    assert json.loads((root/'bridge_cleanup_pending.json').read_text())['guest_ids'] == ids
    assert a.close_count == b.close_count == 0 and set(store) == {NEW, OLD, OTHER}


def test_foreign_overlay_prevents_provider_close(tmp_path, monkeypatch):
    store = {}
    store[NEW] = Container(NEW, {'oscombo': '1', 'oscombo.run': 'our-run'}, store)
    env = Env(NEW, store)
    env.provider._oscombo_overlay = str(tmp_path / 'another-run' / 'disk.qcow2')
    install_fake_docker(monkeypatch, store)
    with pytest.raises(RuntimeError, match='overlay is outside'):
        runner._cleanup_exact_guest('A', env, {'A': NEW}, 'our-run', tmp_path / 'our-run')
    assert env.close_count == 0 and NEW in store
