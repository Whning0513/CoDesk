"""The detached supervisor persists identity and forwards termination."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import time


def test_supervisor_records_pid_exit_and_stops_its_runner(tmp_path):
    repo = tmp_path / 'repo'
    audit = repo / 'audits' / 'three_lite_cases_20261029'
    audit.mkdir(parents=True)
    source = (Path(__file__).resolve().parents[1] / 'audits' / 'three_lite_cases_20261029'
              / 'run_case5_triad_supervisor.sh')
    supervisor = audit / source.name
    shutil.copy2(source, supervisor)
    runner = audit / 'run_case5_model.sh'
    runner.write_text("#!/bin/bash\ntrap 'printf stopped > runner-stopped; exit 143' TERM\n"
                      "printf ready > runner-ready\nwhile :; do sleep 0.1; done\n")
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    git = bin_dir / 'git'
    git.write_text('#!/bin/sh\nprintf 0123456789abcdef0123456789abcdef01234567\\n\n')
    git.chmod(0o755)
    env = {**os.environ, 'PATH': f"{bin_dir}:{os.environ['PATH']}"}
    stamp = '20261031T123456Z'
    process = subprocess.Popen(['bash', str(supervisor), stamp], cwd=repo, env=env,
                               start_new_session=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        ready = repo / 'runner-ready'
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            assert process.poll() is None
            time.sleep(0.02)
        assert ready.exists()
        prefix = audit / f'case5-triad1-{stamp}'
        metadata = json.loads(Path(f'{prefix}-supervisor.json').read_text())
        assert metadata['supervisor_pid'] == process.pid and metadata['start_ticks'] > 0
        assert Path(f'{prefix}-supervisor.pid').read_text().strip() == str(process.pid)
        process.terminate()
        assert process.wait(timeout=5) == 143
        assert Path(f'{prefix}-exit-code.txt').read_text().strip() == '143'
        assert (repo / 'runner-stopped').read_text() == 'stopped'
    finally:
        if process.poll() is None:
            os.killpg(process.pid, 9)
            process.wait(timeout=5)
