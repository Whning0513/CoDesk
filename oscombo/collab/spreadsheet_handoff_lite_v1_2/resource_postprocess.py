"""Read versioned run sampler without mutating existing run evidence."""
from __future__ import annotations
import argparse
import json
from collections import defaultdict
from pathlib import Path


def summarize(path: Path) -> dict:
    samples = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    groups: dict[tuple, list[float]] = defaultdict(list)
    rss_sums, rss_single, guest_counts = [], [], []
    for sample in samples:
        guests = sample.get('guests')
        if not isinstance(guests, list):
            raise ValueError('missing versioned guests list')
        guest_counts.append(len(guests))
        rss_sums.append(sum(g['rss_bytes'] for g in guests))
        for guest in guests:
            identity = (guest['container_id'], guest['pid'])
            groups[identity].append(guest['cpu_seconds'])
            rss_single.append(guest['rss_bytes'])
    return {'sample_count': len(samples), 'process_count': len(groups),
            'max_concurrent_guests': max(guest_counts, default=0),
            'qemu_cpu_seconds_observed_delta': round(sum(max(v)-min(v) for v in groups.values()), 3) if groups else None,
            'qemu_peak_single_rss_gib': round(max(rss_single)/2**30, 3) if rss_single else None,
            'qemu_peak_concurrent_sum_rss_gib': round(max(rss_sums)/2**30, 3) if groups else None,
            'scope': 'Sampled across full run including setup and resets; CPU deltas are lower bounds, not model-only cost.'}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('resource_samples', type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.resource_samples), indent=2))


if __name__ == '__main__':
    main()
