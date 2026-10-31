"""SSE compatibility probes retain status/usage, not content or credentials."""

import importlib.util
import json
from pathlib import Path

import requests


SCRIPT = (Path(__file__).resolve().parents[1] / 'audits' / 'three_lite_cases_20261029'
          / 'case5_endpoint_stream_probe.py')
module_spec = importlib.util.spec_from_file_location('case5_endpoint_stream_probe', SCRIPT)
probe_module = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(probe_module)


def test_stream_probe_records_tool_and_usage_without_payload(monkeypatch):
    secret = 'test-private-content-not-for-logs'
    events = [
        {'type': 'response.output_item.done', 'item': {'type': 'function_call',
         'name': 'report_visible', 'arguments': secret}},
        {'type': 'response.completed', 'response': {'status': 'completed',
         'usage': {'input_tokens': 42, 'output_tokens': 8, 'total_tokens': 50, 'text': secret},
         'output': [{'type': 'function_call', 'name': 'report_visible', 'arguments': secret}]}},
    ]

    class Response:
        status_code = 200
        closed = False

        def iter_lines(self, decode_unicode):
            for event in events:
                yield ('data: ' + json.dumps(event)).encode()
            yield b'data: [DONE]'

        def close(self):
            self.closed = True

    response = Response()
    monkeypatch.setattr(probe_module.requests, 'post', lambda *args, **kwargs: response)
    result = probe_module.probe('endpoint', 'https://example.invalid', secret, {})
    assert result['completed_event'] and result['function_call_seen']
    assert result['usage'] == {'input_tokens': 42, 'output_tokens': 8, 'total_tokens': 50}
    assert secret not in json.dumps(result)
    assert response.closed


def test_stream_interruption_is_retained_as_noncompletion(monkeypatch):
    class Response:
        status_code = 200

        def iter_lines(self, decode_unicode):
            yield 'data: {"type":"response.created"}'
            raise requests.exceptions.ChunkedEncodingError('sensitive response body')

        def close(self):
            pass

    monkeypatch.setattr(probe_module.requests, 'post', lambda *args, **kwargs: Response())
    result = probe_module.probe('endpoint', 'https://example.invalid', 'key', {})
    assert not result['completed_event']
    assert result['error_type'] == 'ChunkedEncodingError'
    assert 'sensitive response body' not in json.dumps(result)
