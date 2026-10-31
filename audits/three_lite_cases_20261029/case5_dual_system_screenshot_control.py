"""Two real Guests: prove same-number system actions retain independent screenshots."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import threading
import time
import traceback

import docker
from PIL import Image

from case5_guest_lifecycle_smoke import host_samples, owned_qemu_processes, watch_probe
from oscombo.collab.data_to_deck import live_pilot as core
from oscombo.collab.data_to_deck.provenance import RunLedger


def verify_first_system_actions(root, b_before):
    a_path = root / 'screenshots' / 'A-system-001.png'
    b_path = root / 'screenshots' / 'B-system-001.png'
    b_after = hashlib.sha256(b_path.read_bytes()).hexdigest()
    if not a_path.is_file() or b_before != b_after:
        raise RuntimeError('A action overwrote or failed to retain B system screenshot')
    for path in (a_path, b_path):
        with Image.open(path) as image_obj:
            image_obj.verify()
    actions = [json.loads(line) for line in (root / 'gui_actions.jsonl').read_text().splitlines()]
    if [(x['guest_key'], x['actor'], x['action_id'], x['screenshot']) for x in actions[:2]] != [
        ('B', 'system', 'B-system-001', 'screenshots/B-system-001.png'),
        ('A', 'system', 'A-system-001', 'screenshots/A-system-001.png')]:
        raise RuntimeError('system action Guest/role/path metadata mismatch')
    return {
        'A': {'role': 'system', 'guest': 'A', 'path': str(a_path.relative_to(root)),
              'sha256': hashlib.sha256(a_path.read_bytes()).hexdigest()},
        'B': {'role': 'system', 'guest': 'B', 'path': str(b_path.relative_to(root)),
              'sha256_before_A': b_before, 'sha256_after_A': b_after},
        'paths_distinct': a_path != b_path, 'B_unchanged_after_A': True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-root', required=True, type=Path)
    args = parser.parse_args()
    root = args.run_root.resolve()
    if not root.name.startswith('case5-dual-system-health-'):
        raise ValueError('run_id must use the dedicated dual-Guest control prefix')
    root.mkdir(parents=True, exist_ok=False)
    run_id = root.name
    start = time.time()
    ledger = RunLedger(root, {'run_id': run_id, 'kind': 'dual_system_screenshot_control',
                              'model_called': False, 'started_at': start})
    core._write_ownership(root, {'project': 'CoDesk dual Guest system screenshot control',
                                 'run_id': run_id, 'resources': [],
                                 'cleanup': 'full ID, exact oscombo.run label, own overlay'})
    provider = Path(os.environ['OSWORLD_DIR']).resolve()
    image = str(Path(os.environ['OSCOMBO_GUEST_IMAGE']).resolve())
    runtime = os.environ['OSCOMBO_RUNTIME_IMAGE']
    result = {'run_id': run_id, 'model_called': False, 'status': 'INVALID_INFRA_OR_RUNNER_ERROR',
              'inotify_before': watch_probe()}
    envs, guests, ids, resets = {}, {}, {}, []
    stop = threading.Event()
    host_thread = threading.Thread(target=host_samples, args=(root, stop), daemon=True)
    guest_thread = threading.Thread(target=core._sample_guest_resources, args=(root, ids, stop), daemon=True)
    host_thread.start()
    guest_thread.start()

    def handle_term(signum, frame):
        raise InterruptedError(f'received signal {signum}; entering run-owned cleanup')

    previous_handler = signal.signal(signal.SIGTERM, handle_term)
    try:
        for key in ('A', 'B'):
            envs[key], guests[key], ids[key] = core._boot_guest(root, run_id, key, image, provider, runtime, ledger)
            (root / 'screenshots' / f'{key}-before-input.png').write_bytes(guests[key].screenshot(patience=45))
            core._shell(guests[key], f'touch /tmp/{run_id}-marker', timeout=30)
        # Both separate LoggedGuest instances execute their first system input.
        # The B file is hashed before and after A acts to detect overwrite.
        guests['B'].run_pyautogui("import pyautogui,time; pyautogui.press('win'); time.sleep(3)")
        b_path = root / 'screenshots' / 'B-system-001.png'
        b_before = hashlib.sha256(b_path.read_bytes()).hexdigest()
        guests['A'].run_pyautogui("import pyautogui,time; pyautogui.press('win'); time.sleep(3)")
        result['screenshot_control'] = verify_first_system_actions(root, b_before)
        core._append(root / 'stages.jsonl', {'stage': 'dual_screenshots_verified',
                     'time': time.time(), **result['screenshot_control']})
        for key in ('B', 'A'):
            guests[key].run_pyautogui("import pyautogui,time; pyautogui.press('esc'); time.sleep(2)")
        for key in ('A', 'B'):
            env, guest, old_id = envs[key], guests[key], ids[key]
            core._verify_container(old_id, run_id)
            os.environ['OSCOMBO_OVERLAY_DIR'] = str(root / 'overlay' / key)
            os.environ['SWCUB_VM_OVERLAY'] = str(root / 'overlay' / key)
            os.environ['OSCOMBO_RUN_LABEL'] = run_id
            env.is_environment_used = True
            env.reset()
            new_container, labels = core._owned_container(env, run_id)
            ids[key] = new_container.id
            if new_container.id == old_id or not core._missing_container(old_id):
                raise RuntimeError(f'{key} reset did not replace its exact container')
            core._shell(guest, f'test ! -e /tmp/{run_id}-marker', timeout=30)
            original_key = guest.guest_key
            guest.guest_key = f'{key}-reset'
            try:
                screenshot = core._wait_for_visible_desktop(guest)
            finally:
                guest.guest_key = original_key
            (root / 'screenshots' / f'{key}-after-reset.png').write_bytes(screenshot)
            entry = {'guest': key, 'old': old_id, 'new': new_container.id,
                     'workspace_clean': True, 'labels': labels}
            resets.append(entry)
            core._append(root / 'stages.jsonl', {'stage': 'reset_verified', 'time': time.time(), **entry})
        result['reset'] = resets
        result['status'] = 'PASS_PENDING_CLEANUP'
    except Exception as exc:
        result.update({'status': 'INVALID_INFRA_OR_RUNNER_ERROR',
                       'error': f'{type(exc).__name__}: {exc}', 'traceback': traceback.format_exc(),
                       'reset': resets})
    finally:
        stop.set()
        host_thread.join(timeout=10)
        guest_thread.join(timeout=15)
        cleanup = []
        try:
            client = docker.from_env(timeout=10)
            for item in client.containers.list(all=True, filters={'label': ['oscombo=1', f'oscombo.run={run_id}']}):
                owned = core._verify_container(item.id, run_id)
                owned.stop(timeout=10)
                owned.remove(force=True)
                if not core._missing_container(item.id):
                    raise RuntimeError(f'run-owned container still exists: {item.id}')
                cleanup.append({'container_id': item.id, 'removed': True})
            client.close()
        except Exception as exc:
            cleanup.append({'error': f'{type(exc).__name__}: {exc}'})
        survivors = owned_qemu_processes(root)
        if survivors:
            cleanup.append({'error': 'run-owned QEMU still exists', 'processes': survivors})
        result['cleanup'] = cleanup
        result['cleanup_complete'] = not any('error' in row for row in cleanup)
        result['inotify_after'] = watch_probe()
        if not result['cleanup_complete']:
            result['status'] = 'INVALID_INFRA_OR_RUNNER_ERROR'
        elif result['status'] == 'PASS_PENDING_CLEANUP':
            result['status'] = 'PASS'
        result['elapsed_s'] = round(time.time() - start, 3)
        (root / 'result.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
        signal.signal(signal.SIGTERM, previous_handler)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['status'] == 'PASS' else 3


if __name__ == '__main__':
    raise SystemExit(main())
