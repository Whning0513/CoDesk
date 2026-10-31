"""Read-only host resource sampling for one Case 5 run."""

import argparse
import json
import os
from pathlib import Path
import shutil
import time


def inotify_watch_count():
    total, denied = 0, 0
    uid = os.getuid()
    for proc in Path('/proc').iterdir():
        if not proc.name.isdecimal():
            continue
        try:
            if proc.stat().st_uid != uid:
                continue
            for fdinfo in (proc / 'fdinfo').iterdir():
                try:
                    total += sum(line.startswith('inotify wd:') for line in fdinfo.read_text().splitlines())
                except (OSError, UnicodeError):
                    denied += 1
        except OSError:
            denied += 1
    return {'count_lower_bound': total, 'unreadable_process_or_fdinfo': denied,
            'max_user_watches': int(Path('/proc/sys/fs/inotify/max_user_watches').read_text())}


def sample(root, interval, max_seconds):
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    started, last_watch = time.monotonic(), 0.0
    while time.monotonic() - started < max_seconds:
        mem = {}
        for line in Path('/proc/meminfo').read_text().splitlines():
            key, _, value = line.partition(':')
            if key in {'MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'}:
                mem[key] = value.strip()
        row = {'time': time.time(), 'loadavg': os.getloadavg(), 'cpu_count': os.cpu_count(),
               'cpu_counters': Path('/proc/stat').read_text().splitlines()[0],
               'meminfo': mem, 'disk_free_bytes': shutil.disk_usage(root).free,
               'io_pressure': Path('/proc/pressure/io').read_text().strip()}
        now = time.monotonic()
        if now - last_watch >= 60:
            row['inotify'] = inotify_watch_count()
            last_watch = now
        with (root / 'host_resources.jsonl').open('a') as stream:
            stream.write(json.dumps(row, sort_keys=True) + '\n')
        time.sleep(interval)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('run_root', type=Path)
    parser.add_argument('--interval', type=float, default=5)
    parser.add_argument('--max-seconds', type=float, default=3600)
    args = parser.parse_args()
    sample(args.run_root, args.interval, args.max_seconds)
