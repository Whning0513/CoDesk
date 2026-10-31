"""The dual-Guest control rejects a changed or misattributed earlier screenshot."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

from PIL import Image
import pytest


SCRIPT = (Path(__file__).resolve().parents[1] / 'audits' / 'three_lite_cases_20261029'
          / 'case5_dual_system_screenshot_control.py')
sys.path.insert(0, str(SCRIPT.parent))
try:
    module_spec = importlib.util.spec_from_file_location('case5_dual_screenshot_control', SCRIPT)
    control = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(control)
finally:
    sys.path.pop(0)


@pytest.mark.parametrize('fault', [None, 'changed_b', 'metadata'])
def test_dual_first_action_control_detects_overwrite(tmp_path, fault):
    shots = tmp_path / 'screenshots'
    shots.mkdir()
    a, b = shots / 'A-system-001.png', shots / 'B-system-001.png'
    Image.new('RGB', (8, 8), 'red').save(a)
    Image.new('RGB', (8, 8), 'blue').save(b)
    before = hashlib.sha256(b.read_bytes()).hexdigest()
    rows = [{'guest_key': 'B', 'actor': 'system', 'action_id': 'B-system-001',
             'screenshot': 'screenshots/B-system-001.png'},
            {'guest_key': 'A', 'actor': 'system', 'action_id': 'A-system-001',
             'screenshot': 'screenshots/A-system-001.png'}]
    if fault == 'changed_b':
        Image.new('RGB', (8, 8), 'green').save(b)
    if fault == 'metadata':
        rows[1]['screenshot'] = rows[0]['screenshot']
    (tmp_path / 'gui_actions.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
    if fault:
        with pytest.raises(RuntimeError):
            control.verify_first_system_actions(tmp_path, before)
    else:
        report = control.verify_first_system_actions(tmp_path, before)
        assert report['paths_distinct'] and report['B_unchanged_after_A']
        assert report['B']['sha256_before_A'] == report['B']['sha256_after_A']
