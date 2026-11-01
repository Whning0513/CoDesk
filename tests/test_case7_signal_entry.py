"""Exercise the actual bootstrap in a child inheriting SIGINT=SIG_IGN."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest


@pytest.mark.parametrize('cleanup_raises', [False, True])
def test_background_ignored_sigint_enters_finally_and_preserves_failure(tmp_path, cleanup_raises):
    ready = tmp_path / 'ready'
    cleanup = tmp_path / 'cleanup'
    code = '''
import pathlib, time
from oscombo.collab.workspace_assembly_lite_v2p1 import signal_entry
ready, marker = pathlib.Path(%r), pathlib.Path(%r)
def driver(*args, **kwargs):
    try:
        ready.write_text('ready')
        while True: time.sleep(0.05)
    finally:
        marker.write_text('cleanup entered')
        if %r: raise RuntimeError('synthetic cleanup failure')
signal_entry.runpy.run_module = driver
signal_entry.main()
''' % (str(ready), str(cleanup), cleanup_raises)
    proc = subprocess.Popen([sys.executable, '-c', code], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN))
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists(), 'bootstrap did not start driver'
        proc.send_signal(signal.SIGINT)
        _, stderr = proc.communicate(timeout=10)
        assert proc.returncode != 0
        assert cleanup.read_text() == 'cleanup entered'
        assert b'KeyboardInterrupt' in stderr
        if cleanup_raises:
            assert b'synthetic cleanup failure' in stderr
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def test_wrapper_uses_signal_bootstrap_for_only_its_driver():
    wrapper = (Path(__file__).resolve().parents[1] /
               'audits/three_lite_cases_20261029/run_case7_v2p1_one.sh').read_text()
    assert '"$python" -m oscombo.collab.workspace_assembly_lite_v2p1.signal_entry' in wrapper
    assert 'driver_pid=$!' in wrapper and 'wait "$driver_pid"' in wrapper
