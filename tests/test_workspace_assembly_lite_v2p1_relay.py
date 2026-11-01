"""v2.1 gates reject relay errors even if upstream sent HTTP 200."""
import json
from pathlib import Path
import pytest
from oscombo.collab.workspace_assembly_lite_v2p1 import campaign, contract, freeze


def make_run(root: Path, event: dict) -> None:
    root.mkdir()
    normal = {'time': 10, 'started_at': 9, 'actor': 'B', 'actor_mcp_only': True,
              'upstream_status': 200, 'headers_sent': True, 'forwarded_bytes': 20}
    (root / 'codex_relay_events.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in (normal, event)))
    for role in 'AB':
        log = root / f'actor_runs/{role}/{role}/stdout.log'
        log.parent.mkdir(parents=True)
        log.write_text(json.dumps({'type': 'item.started', 'item': {
            'id': '1', 'type': 'mcp_tool_call', 'server': 'desktop'}})+'\n')
    (root / 'resource_audit.json').write_text('{"valid":true}')
    (root / 'model_metrics_v2.json').write_text('{"lifecycle_errors":[]}')
    (root / 'missing_outputs.json').write_text('[]')
    (root / 'result.json').write_text(json.dumps({
        'status': 'FAIL', 'postscore_lifecycle_ok': True, 'bridge_valid': True,
        'oracle_fixture_valid': True, 'reopen': [{'role': 'A', 'same_bytes': True},
                                                {'role': 'B', 'same_bytes': True}]}))


def test_v2p1_http200_broken_pipe_is_never_clean_even_with_stale_audit(tmp_path, monkeypatch):
    root = tmp_path / 'run'
    # Exact relevant fields observed in the Pilot, synthetic timestamps.
    broken = {'time': 20, 'started_at': 11, 'actor': 'A', 'error_type': 'BrokenPipeError',
              'phase': 'downstream_write', 'headers_sent': True, 'forwarded_bytes': 0,
              'upstream_status': 200, 'actor_mcp_only': True, 'elapsed_s': 9}
    make_run(root, broken)
    audit = contract.audit(root)
    assert not audit['valid'] and any('review transport' in e for e in audit['errors'])
    (root / 'contract_audit.json').write_text(json.dumps({**audit, 'valid': True, 'errors': []}))
    assert campaign.classify(root, 2) == 'INVALID_INFRA'
    meta = {'model_called': True, 'model': 'gpt-6-astra', 'model_effort': 'medium',
            'model_timeout': 600, 'diagnostic_step_limit': 12, 'actor_mcp_only': True,
            'yield_wait_lifecycle': True}
    monkeypatch.setattr(freeze, '_common', lambda *a, **kw: (meta, {'status': 'FAIL'}))
    with pytest.raises(ValueError, match='Pilot relay/allowlist'):
        freeze._pilot(root, 'commit', root / 'review.json')


@pytest.mark.parametrize('fields', [
    {'upstream_status': None, 'error_type': 'SSLError', 'headers_sent': False, 'forwarded_bytes': 0},
    {'upstream_status': 200, 'error_type': 'ChunkedEncodingError', 'headers_sent': True, 'forwarded_bytes': 42},
    {'upstream_status': 200, 'error_type': 'BrokenPipeError', 'cancelled_after_budget': True},
    {'upstream_status': 200, 'error_type': None},
    {'upstream_status': 200, 'headers_sent': False},
    {'upstream_status': 200, 'forwarded_bytes': None},
    {'upstream_status': 200, 'phase': 'upstream_stream'},
    {'upstream_status': None}, {}, {'actor': []}, {'upstream_status': [200]},
])
def test_v2p1_unknown_error_and_cancel_are_transport_review(tmp_path, fields):
    event = {'actor': 'A', 'actor_mcp_only': True, 'headers_sent': True, 'forwarded_bytes': 20, **fields}
    root = tmp_path / 'run'; make_run(root, event)
    result = contract.audit(root)
    assert not result['valid'] and any('review transport' in e for e in result['errors'])


def test_v2p1_normal_200_and_missing_fields(tmp_path):
    good = {'actor': 'A', 'actor_mcp_only': True, 'upstream_status': 200,
            'headers_sent': True, 'forwarded_bytes': 20}
    root = tmp_path / 'run'; make_run(root, good)
    clean = contract.audit(root)
    assert clean['valid'] and contract.relay_event_clean(good)
    for key in ('actor', 'actor_mcp_only', 'upstream_status', 'headers_sent', 'forwarded_bytes'):
        bad = dict(good); bad.pop(key)
        assert not contract.relay_event_clean(bad)
    assert not contract.relay_event_clean({'actor': 'other', 'actor_mcp_only': True, 'upstream_status': 200})
    assert not contract.relay_event_clean(None)
    (root / 'contract_audit.json').write_text(json.dumps(clean))
    assert campaign.classify(root, 2) == 'VALID_FAIL'


@pytest.mark.parametrize('value', [0, -1, True, False, None, '20', 1.0, [], {}])
def test_v2p1_rejects_empty_or_invalid_forwarded_bytes(tmp_path, value):
    root = tmp_path / 'run'
    make_run(root, {'actor': 'A', 'actor_mcp_only': True, 'upstream_status': 200,
                    'headers_sent': True, 'forwarded_bytes': value})
    out = contract.audit(root)
    assert not out['valid'] and any('review transport' in error for error in out['errors'])


@pytest.mark.parametrize('key', ['headers_sent', 'forwarded_bytes'])
def test_v2p1_missing_success_fields_fail_all_gates(tmp_path, monkeypatch, key):
    root = tmp_path / 'run'
    row = {'actor': 'A', 'actor_mcp_only': True, 'upstream_status': 200,
           'headers_sent': True, 'forwarded_bytes': 20}
    row.pop(key)
    make_run(root, row)
    out = contract.audit(root)
    assert not out['valid'] and any('review transport' in e for e in out['errors'])
    (root / 'contract_audit.json').write_text(json.dumps({**out, 'valid': True, 'errors': []}))
    assert campaign.classify(root, 2) == 'INVALID_INFRA'
    meta = {'model_called': True, 'model': 'gpt-6-astra', 'model_effort': 'medium',
            'model_timeout': 600, 'diagnostic_step_limit': 12, 'actor_mcp_only': True,
            'yield_wait_lifecycle': True}
    monkeypatch.setattr(freeze, '_common', lambda *a, **kw: (meta, {'status': 'FAIL'}))
    with pytest.raises(ValueError, match='Pilot relay/allowlist'):
        freeze._pilot(root, 'commit', root / 'review.json')
