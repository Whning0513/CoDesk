"""Offline tests: deadline includes HTTP stalls and kills only the helper."""
from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from oscombo.guest import Guest, InfraError


@pytest.fixture
def server_factory():
    servers = []
    def start(handler):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append((server, thread))
        env = SimpleNamespace(controller=SimpleNamespace(http_server=f"http://127.0.0.1:{server.server_port}"))
        return Guest(env)
    yield start
    for server, thread in servers:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def test_screenshot_valid_and_worker_does_not_inherit_provider_key(server_factory, monkeypatch):
    import oscombo.guest as module
    raw = b"\x89PNG\r\n\x1a\n" + b"fake-screenshot"
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_GET(self):
            self.send_response(200); self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
    monkeypatch.setenv("FAKE_PROVIDER_API_KEY", "never-in-helper")
    popen = module.subprocess.Popen
    captured = []
    def start(*args, **kwargs):
        assert "FAKE_PROVIDER_API_KEY" not in kwargs["env"]
        proc = popen(*args, **kwargs); captured.append(proc); return proc
    monkeypatch.setattr(module.subprocess, "Popen", start)
    assert server_factory(Handler).screenshot(3) == raw
    assert len(captured) == 1 and captured[0].poll() == 0


@pytest.mark.parametrize("behavior", ["blocked", "slow_drip", "disconnect"])
def test_screenshot_deadline_and_helper_reaped(server_factory, monkeypatch, behavior):
    import oscombo.guest as module
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_GET(self):
            if behavior == "disconnect":
                self.close_connection = True
                return
            if behavior == "blocked":
                time.sleep(2)
                return
            self.send_response(200); self.send_header("Content-Type", "image/png"); self.end_headers()
            try:
                while True:
                    self.wfile.write(b"x"); self.wfile.flush(); time.sleep(.08)
            except (BrokenPipeError, ConnectionResetError):
                pass
    popen = module.subprocess.Popen
    captured = []
    def start(*args, **kwargs):
        proc = popen(*args, **kwargs); captured.append(proc); return proc
    monkeypatch.setattr(module.subprocess, "Popen", start)
    guest = server_factory(Handler)
    start_time = time.monotonic()
    with pytest.raises(InfraError):
        guest.screenshot(.7)
    elapsed = time.monotonic() - start_time
    assert elapsed < 1.5
    assert len(captured) == 1 and captured[0].poll() is not None


def test_nonpositive_deadline_does_not_start_helper(server_factory, monkeypatch):
    import oscombo.guest as module
    monkeypatch.setattr(module.subprocess, "Popen", lambda *_a, **_k: pytest.fail("unexpected helper"))
    with pytest.raises(InfraError):
        Guest(SimpleNamespace()).screenshot(0)


def test_interruption_reaps_helper(monkeypatch):
    import oscombo.guest as module
    real_popen = module.subprocess.Popen
    captured = []
    class InterruptOnce:
        def __init__(self, proc):
            self.proc = proc
            self.calls = 0
        @property
        def args(self): return self.proc.args
        @property
        def returncode(self): return self.proc.returncode
        def poll(self): return self.proc.poll()
        def kill(self): return self.proc.kill()
        def communicate(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise KeyboardInterrupt
            return self.proc.communicate(*args, **kwargs)
    def start(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        captured.append(proc)
        return InterruptOnce(proc)
    monkeypatch.setattr(module.subprocess, "Popen", start)
    guest = Guest(SimpleNamespace(controller=SimpleNamespace(http_server="http://127.0.0.1:9")))
    with pytest.raises(KeyboardInterrupt):
        guest.screenshot(3)
    assert len(captured) == 1 and captured[0].poll() is not None
