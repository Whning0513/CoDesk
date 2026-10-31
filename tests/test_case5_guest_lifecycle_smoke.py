"""Offline checks for diagnostic evidence and interruption cleanup."""

import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import sys
from types import SimpleNamespace

from PIL import Image
import pytest


SCRIPT = (Path(__file__).resolve().parents[1] / 'audits' / 'three_lite_cases_20261029'
          / 'case5_guest_lifecycle_smoke.py')
module_spec = importlib.util.spec_from_file_location('case5_guest_lifecycle_smoke', SCRIPT)
smoke = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(smoke)


@pytest.mark.parametrize('mode', ['success', 'interrupt', 'orphan'])
def test_editor_evidence_and_run_owned_cleanup_on_term(tmp_path, monkeypatch, capsys, mode):
    interrupt = mode == 'interrupt'
    root = tmp_path / f'case5-lifecycle-health-{mode}'
    screenshots = []
    for color in ('black', 'white'):
        buf = io.BytesIO()
        Image.new('RGB', (1920, 1080), color).save(buf, format='PNG')
        screenshots.append(buf.getvalue())

    class Container:
        id = 'new-container'
        removed = False
        stopped = False

        def stop(self, timeout):
            self.stopped = True

        def remove(self, force):
            self.removed = True

    container = Container()
    labels = {'oscombo': '1', 'oscombo.run': root.name}
    env = SimpleNamespace(controller=SimpleNamespace(get_file=lambda path: b'saved review\n'),
                          is_environment_used=False, reset=lambda: None)

    class Guest:
        guest_key = 'A'
        actor = 'system'

        def __init__(self):
            self.env = env
            self.count = 0

        def screenshot(self, patience):
            self.count += 1
            return screenshots[0] if self.count == 1 else screenshots[1]

        def run_pyautogui(self, code):
            pass

        def active_window(self):
            return 'shade_review.txt - Text Editor'

    guest = Guest()

    def boot(root_path, *args):
        (root_path / 'screenshots').mkdir(exist_ok=True)
        return env, guest, 'old-container'

    def verify(cid, run_id):
        assert cid == container.id and run_id == root.name
        return container

    # The old Guest is checked before reset, and the new one for cleanup.
    monkeypatch.setattr(smoke.core, '_verify_container',
                        lambda cid, run_id: None if cid == 'old-container' else verify(cid, run_id))
    monkeypatch.setattr(smoke.core, '_boot_guest', boot)
    monkeypatch.setattr(smoke.core, '_owned_container', lambda *args: (container, labels))
    monkeypatch.setattr(smoke.core, '_missing_container',
                        lambda cid: cid == 'old-container' or (cid == container.id and container.removed))
    monkeypatch.setattr(smoke.core, '_shell', lambda *args, **kwargs: {'status': 'success', 'output': ''})
    monkeypatch.setattr(smoke.core, '_sample_guest_resources', lambda *args: None)
    monkeypatch.setattr(smoke, 'host_samples', lambda *args: None)
    monkeypatch.setattr(smoke, 'watch_probe', lambda: {'allocated': 2})
    monkeypatch.setattr(smoke, 'owned_qemu_processes',
                        lambda root_path: [{'pid': 123, 'matched_run_overlay': True}] if mode == 'orphan' else [])
    monkeypatch.setattr(smoke.fixtures, 'build_fixture', lambda path: path.mkdir())
    monkeypatch.setattr(smoke.adapter, '_install', lambda *args: None)
    monkeypatch.setattr(smoke.adapter, '_launch', lambda *args: None)
    monkeypatch.setattr(smoke.adapter, '_activate_or_restore_saved_editor', lambda *args: True)

    def wait_for_desktop(_guest):
        if interrupt:
            os.kill(os.getpid(), signal.SIGTERM)
        return screenshots[1]

    monkeypatch.setattr(smoke.core, '_wait_for_visible_desktop', wait_for_desktop)
    client = SimpleNamespace(containers=SimpleNamespace(list=lambda **kwargs: [container]), close=lambda: None)
    monkeypatch.setattr(smoke.docker, 'from_env', lambda **kwargs: client)
    monkeypatch.setenv('OSWORLD_DIR', str(tmp_path))
    monkeypatch.setenv('OSCOMBO_GUEST_IMAGE', str(tmp_path / 'guest.qcow2'))
    monkeypatch.setenv('OSCOMBO_RUNTIME_IMAGE', 'runtime')
    monkeypatch.setattr(sys, 'argv', ['smoke', '--run-root', str(root), '--editor-reopen'])

    previous_handler = signal.getsignal(signal.SIGTERM)
    assert smoke.main() == (0 if mode == 'success' else 3)
    assert signal.getsignal(signal.SIGTERM) == previous_handler
    result = json.loads((root / 'result.json').read_text())
    stages = [json.loads(line) for line in (root / 'stages.jsonl').read_text().splitlines()]
    assert [stage['stage'] for stage in stages] == ['editor_reopen_verified', 'reset_marker_absent']
    assert (root / 'artifacts' / 'editor_before.txt').read_bytes() == (root / 'artifacts' / 'editor_after.txt').read_bytes()
    assert container.stopped and container.removed
    assert result['cleanup'][0] == {'container_id': container.id, 'removed': True}
    assert result['status'] == ('PASS' if mode == 'success' else 'INVALID_INFRA_OR_RUNNER_ERROR')
    assert result['cleanup_complete'] is (mode != 'orphan')
    if mode == 'orphan':
        assert result['cleanup'][1]['error'] == 'run-owned QEMU still exists'
    if interrupt:
        assert 'received signal' in result['error']
    capsys.readouterr()
