"""One run-owned OSWorld Guest lifecycle health check; no model or task score."""

import argparse
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import tempfile
import threading
import time
import traceback

import docker
from PIL import Image, ImageChops, ImageStat

from oscombo.collab.data_to_deck.provenance import RunLedger
from oscombo.collab.data_to_deck import live_pilot as core
from oscombo.collab import lite_file_guest_pilot as adapter
from oscombo.collab.model_and_review_lite_v1 import fixtures, spec


def watch_probe():
    lib = ctypes.CDLL(None, use_errno=True)
    fd = lib.inotify_init1(os.O_CLOEXEC)
    if fd < 0:
        return {"init_errno": ctypes.get_errno()}
    count, error = 0, 0
    try:
        with tempfile.TemporaryDirectory(prefix="codesk-watch-probe-") as root:
            for i in range(64):
                path = Path(root) / str(i)
                path.mkdir()
                if lib.inotify_add_watch(fd, os.fsencode(path), 0x100) < 0:
                    error = ctypes.get_errno()
                    break
                count += 1
    finally:
        os.close(fd)
    return {"allocated": count, "requested": 64, "errno": error,
            "error_name": errno.errorcode.get(error),
            "max_user_watches": int(Path('/proc/sys/fs/inotify/max_user_watches').read_text())}


def host_samples(root, stop):
    while not stop.is_set():
        try:
            mem = {}
            for line in Path('/proc/meminfo').read_text().splitlines():
                key, _, val = line.partition(':')
                if key in {'MemAvailable', 'SwapTotal', 'SwapFree'}:
                    mem[key] = val.strip()
            pressure = Path('/proc/pressure/io').read_text().strip()
            core._append(root / 'host_resources.jsonl', {
                'time': time.time(), 'loadavg': os.getloadavg(), 'meminfo': mem,
                'disk_free_bytes': shutil.disk_usage(root).free, 'io_pressure': pressure})
        except Exception as exc:
            core._append(root / 'host_resources.jsonl', {'time': time.time(), 'error': repr(exc)})
        stop.wait(5)


def owned_qemu_processes(root):
    """Find a surviving QEMU only when its overlay basename belongs to this run."""
    names = {p.name for p in (root / 'overlay').rglob('*.qcow2')}
    found = []
    if not names:
        return found
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            command = (entry / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
        except OSError:
            continue
        if 'qemu-system-x86_64' in command and any(name in command for name in names):
            found.append({'pid': int(entry.name), 'matched_run_overlay': True})
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-root', required=True, type=Path)
    parser.add_argument('--editor-reopen', action='store_true',
                        help='test the production postscore closed-editor recovery path')
    args = parser.parse_args()
    root = args.run_root.resolve()
    if not root.name.startswith('case5-lifecycle-health-'):
        raise ValueError('run_id must use the dedicated health-check prefix')
    root.mkdir(parents=True, exist_ok=False)
    run_id = root.name
    ledger = RunLedger(root, {'run_id': run_id, 'kind': 'guest_lifecycle_health',
                              'model_called': False, 'started_at': time.time()})
    core._write_ownership(root, {'project': 'CoDesk Case 5 lifecycle health',
                                 'run_id': run_id, 'resources': [],
                                 'cleanup': 'full container ID and exact oscombo.run label'})
    provider = Path(os.environ['OSWORLD_DIR']).resolve()
    image = str(Path(os.environ['OSCOMBO_GUEST_IMAGE']).resolve())
    runtime = os.environ['OSCOMBO_RUNTIME_IMAGE']
    result = {'run_id': run_id, 'model_called': False, 'status': 'INVALID_INFRA_OR_RUNNER_ERROR',
              'inotify_before': watch_probe(), 'events': []}
    env, guest, cid = None, None, None
    ids, stop = {}, threading.Event()
    host_thread = threading.Thread(target=host_samples, args=(root, stop), daemon=True)
    guest_thread = threading.Thread(target=core._sample_guest_resources,
                                    args=(root, ids, stop), daemon=True)
    host_thread.start()
    guest_thread.start()
    def handle_term(signum, frame):
        raise InterruptedError(f'received signal {signum}; entering run-owned cleanup')
    previous_term_handler = signal.signal(signal.SIGTERM, handle_term)
    try:
        env, guest, cid = core._boot_guest(root, run_id, 'A', image, provider, runtime, ledger)
        ids['A'] = cid
        start = time.monotonic()
        before = guest.screenshot(patience=45)
        (root / 'screenshots' / 'before-input.png').write_bytes(before)
        result['screenshot_before_s'] = round(time.monotonic() - start, 3)
        guest.actor = 'system'
        guest.run_pyautogui("import pyautogui,time; pyautogui.press('win'); time.sleep(3)")
        overview = guest.screenshot(patience=45)
        (root / 'screenshots' / 'after-super.png').write_bytes(overview)
        from io import BytesIO
        with Image.open(BytesIO(before)) as first, Image.open(BytesIO(overview)) as second:
            if first.size != second.size:
                raise RuntimeError('Guest screenshot size changed unexpectedly')
            difference = ImageStat.Stat(ImageChops.difference(first.convert('RGB'), second.convert('RGB'))).mean
            result['gui_frame_mean_difference'] = round(sum(difference) / len(difference), 3)
        if result['gui_frame_mean_difference'] < 1.0:
            raise RuntimeError('Super input did not visibly change the Guest desktop')
        guest.run_pyautogui("import pyautogui,time; pyautogui.press('esc'); time.sleep(2)")
        task_root = '/tmp/codesk-model-review-lite-v1'
        if args.editor_reopen:
            fixture_root = root / 'fixtures'
            fixtures.build_fixture(fixture_root)
            adapter._install(guest, fixture_root, task_root, 'model_review', spec)
            report_path = f"{task_root}/{spec.OUTPUTS['B']}"
            saved_before = guest.env.controller.get_file(report_path)
            adapter._launch(guest, 'editor', report_path, run_id)
            (root / 'screenshots' / 'editor-before-close.png').write_bytes(guest.screenshot(patience=45))
            guest.run_pyautogui("import pyautogui,time; pyautogui.hotkey('alt','f4'); time.sleep(3)")
            windows = core._shell(guest, 'wmctrl -l || true', timeout=30).get('output', '')
            if Path(report_path).name.casefold() in windows.casefold():
                raise RuntimeError('GUI close did not remove the report window')
            (root / 'screenshots' / 'editor-after-close.png').write_bytes(guest.screenshot(patience=45))
            restored = adapter._activate_or_restore_saved_editor(guest, 'editor', report_path, run_id, True)
            title = guest.active_window() or ''
            (root / 'screenshots' / 'editor-reopened.png').write_bytes(guest.screenshot(patience=45))
            saved_after = guest.env.controller.get_file(report_path)
            if not restored or Path(report_path).name.casefold() not in title.casefold():
                raise RuntimeError('production postscore path did not restore the report GUI')
            if saved_before != saved_after:
                raise RuntimeError('saved report bytes changed during postscore reopen')
            result['editor_reopen'] = {'production_restore_branch': restored, 'active_title': title,
                                       'same_bytes': True,
                                       'sha256': hashlib.sha256(saved_after).hexdigest()}
            artifacts = root / 'artifacts'
            artifacts.mkdir(exist_ok=True)
            (artifacts / 'editor_before.txt').write_bytes(saved_before)
            (artifacts / 'editor_after.txt').write_bytes(saved_after)
            core._append(root / 'stages.jsonl', {'stage': 'editor_reopen_verified',
                         'time': time.time(), **result['editor_reopen']})
        marker = f'/tmp/{run_id}-reset-marker'
        core._shell(guest, f'touch {marker}', timeout=30)
        old_id = cid
        core._verify_container(old_id, run_id)
        env.is_environment_used = True
        start = time.monotonic()
        env.reset()
        new_container, labels = core._owned_container(env, run_id)
        cid = new_container.id
        ids['A'] = cid
        if cid == old_id or not core._missing_container(old_id):
            raise RuntimeError('reset did not replace the exact run-owned container')
        if core._shell(guest, f'test ! -e {marker} && test ! -e {task_root}', timeout=30).get('status') != 'success':
            raise RuntimeError('reset retained the Guest marker')
        core._append(root / 'stages.jsonl', {'stage': 'reset_marker_absent', 'time': time.time(),
                     'old_container': old_id, 'new_container': cid, 'labels': labels})
        start_shot = time.monotonic()
        original_guest_key = guest.guest_key
        guest.guest_key = 'A-reset'
        try:
            after = core._wait_for_visible_desktop(guest)
        finally:
            guest.guest_key = original_guest_key
        (root / 'screenshots' / 'after-reset.png').write_bytes(after)
        result.update({'reset_s': round(time.monotonic() - start, 3),
                       'screenshot_after_reset_s': round(time.monotonic() - start_shot, 3),
                       'old_container': old_id, 'new_container': cid, 'reset_labels': labels,
                       'reset_replaced_container': True, 'reset_marker_absent': True,
                       'status': 'PASS_PENDING_CLEANUP'})
    except Exception as exc:
        result.update({'status': 'INVALID_INFRA_OR_RUNNER_ERROR', 'error': f'{type(exc).__name__}: {exc}',
                       'traceback': traceback.format_exc()})
    finally:
        stop.set()
        host_thread.join(timeout=10)
        guest_thread.join(timeout=15)
        cleanup = []
        try:
            client = docker.from_env(timeout=10)
            containers = client.containers.list(all=True, filters={'label': ['oscombo=1', f'oscombo.run={run_id}']})
            for item in containers:
                owned = core._verify_container(item.id, run_id)
                owned.stop(timeout=10)
                owned.remove(force=True)
                if not core._missing_container(item.id):
                    raise RuntimeError(f'owned container still exists: {item.id}')
                cleanup.append({'container_id': item.id, 'removed': True})
            client.close()
        except Exception as exc:
            cleanup.append({'error': f'{type(exc).__name__}: {exc}'})
        surviving_qemu = owned_qemu_processes(root)
        if surviving_qemu:
            cleanup.append({'error': 'run-owned QEMU still exists', 'processes': surviving_qemu})
        result['cleanup'] = cleanup
        result['cleanup_complete'] = not any('error' in row for row in cleanup)
        result['inotify_after'] = watch_probe()
        if not result['cleanup_complete']:
            result['status'] = 'INVALID_INFRA_OR_RUNNER_ERROR'
        elif result['status'] == 'PASS_PENDING_CLEANUP':
            result['status'] = 'PASS'
        result['ended_at'] = time.time()
        (root / 'result.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
        signal.signal(signal.SIGTERM, previous_term_handler)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['status'] == 'PASS' else 3


if __name__ == '__main__':
    raise SystemExit(main())
