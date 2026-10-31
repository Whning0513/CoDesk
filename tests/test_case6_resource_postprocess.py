import json
import pytest
from oscombo.collab.spreadsheet_handoff_lite_v1_2.resource_postprocess import summarize


def test_concurrent_peak_and_process_counter_deltas(tmp_path):
    path = tmp_path / 'samples.jsonl'
    def guest(container, pid, cpu, rss):
        return {'container_id': container, 'pid': pid, 'cpu_seconds': cpu, 'rss_bytes': rss}
    rows = [
        {'guests': []},
        {'guests': [guest('a', 1, 10, 2**30), guest('b', 2, 8, 2*2**30)]},
        {'guests': [guest('a', 1, 13, 3*2**30), guest('b', 2, 12, 2**30)]},
        {'guests': [guest('reset', 1, 2, 2**30)]},
        {'guests': [guest('reset', 1, 5, 2**30)]},
    ]
    path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    out = summarize(path)
    assert out['process_count'] == 3
    assert out['max_concurrent_guests'] == 2
    assert out['qemu_cpu_seconds_observed_delta'] == 10
    assert out['qemu_peak_concurrent_sum_rss_gib'] == 4


def test_empty_and_invalid_are_not_misreported_as_measured_zero(tmp_path):
    path = tmp_path / 'samples.jsonl'
    path.write_text('{"guests": []}\n')
    assert summarize(path)['qemu_peak_single_rss_gib'] is None
    path.write_text('{}\n')
    with pytest.raises(ValueError):
        summarize(path)
