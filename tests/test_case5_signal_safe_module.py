"""The detached model driver must enter cleanup when its supervisor stops it."""

import os
from pathlib import Path
import subprocess
import sys
import time


def test_term_unwinds_module_and_runs_cleanup(tmp_path):
    module = tmp_path / 'case5_test_child.py'
    module.write_text("""import os, pathlib, time
p = pathlib.Path(os.environ['CASE5_TEST_DIR'])
(p / 'ready').write_text('ready')
try:
    while True:
        time.sleep(1)
except InterruptedError:
    raise SystemExit(3)
finally:
    (p / 'cleanup').write_text('cleaned')
""")
    wrapper = (Path(__file__).resolve().parents[1] / 'audits' / 'three_lite_cases_20261029'
               / 'case5_signal_safe_module.py')
    env = {**os.environ, 'PYTHONPATH': str(tmp_path), 'CASE5_TEST_DIR': str(tmp_path)}
    process = subprocess.Popen([sys.executable, str(wrapper), 'case5_test_child'], env=env)
    try:
        deadline = time.monotonic() + 5
        while not (tmp_path / 'ready').exists() and time.monotonic() < deadline:
            assert process.poll() is None
            time.sleep(0.02)
        assert (tmp_path / 'ready').exists()
        process.terminate()
        assert process.wait(timeout=5) == 3
        assert (tmp_path / 'cleanup').read_text() == 'cleaned'
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
