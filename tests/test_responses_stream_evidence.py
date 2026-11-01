"""Responses terminal evidence is passive, bounded, and fail-closed."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from oscombo.responses_stream_evidence import ResponseEvidence
from oscombo.responses_tool_image_relay import make_server


@pytest.mark.parametrize('raw,expected', [
    (b'event: response.completed\r\ndata: {"type":\r\ndata: "response.completed"}\r\n\r\n', 'response.completed'),
    (b'data: {"type":"response.completed"}\n\ndata: [DONE]\n\n', 'response.completed'),
    (b': keepalive\n\ndata: {"type":"response.completed"}\n\n', 'response.completed'),
    (b'data: {"type":"response.failed"}\n\n', 'response.failed'),
    (b'data: {"type":"response.incomplete"}\n\n', 'response.incomplete'),
    (b'data: [DONE]\n\n', 'done_only'),
    (b'data: {"type":"response.created"}\n\n', 'missing'),
    (b'data: {"type":"response.completed"}', 'malformed'),
    (b'data: {bad json}\n\n', 'malformed'),
    (b'event: response.completed\ndata: {"type":"response.failed"}\n\n', 'malformed'),
    (b'data: {"type":"response.completed"}\n\ndata: {"type":"response.created"}\n\n', 'malformed'),
    (b'data: \xff\n\n', 'malformed'),
])
def test_sse_all_single_byte_boundaries(raw, expected):
    evidence = ResponseEvidence('text/event-stream; charset=utf-8')
    for byte in raw:
        evidence.feed(bytes([byte]))
    assert evidence.finish() == {'response_format': 'sse', 'response_terminal': expected,
                                 'response_evidence_version': 1}


def test_non_sse_response_is_evaluated_independently():
    cases = [(b'{"object":"response","status":"completed"}', 'response.completed'),
             (b'{"object":"response","status":"failed"}', 'response.failed'),
             (b'{"object":"response","status":"incomplete"}', 'response.incomplete'),
             (b'{"object":"response","status":"in_progress"}', 'missing'),
             (b'{', 'malformed')]
    for raw, expected in cases:
        evidence = ResponseEvidence('application/json; charset=utf-8')
        for i in range(0, len(raw), 3): evidence.feed(raw[i:i+3])
        assert evidence.finish()['response_terminal'] == expected
    unknown = ResponseEvidence('text/plain')
    unknown.feed(b'{"object":"response","status":"completed"}')
    assert unknown.finish()['response_format'] == 'unknown'


@pytest.mark.parametrize('body,mime,expected', [
    (b'data: {"type":"response.completed"}\n\n', 'text/event-stream', 'response.completed'),
    (b'data: {"type":"response.created"}\n\n', 'text/event-stream', 'missing'),
    (b'data: [DONE]\n\n', 'text/event-stream', 'done_only'),
    (b'data: {broken}\n\n', 'text/event-stream', 'malformed'),
    (b'{"object":"response","status":"completed"}', 'application/json', 'response.completed'),
])
def test_loopback_passes_bytes_unchanged_and_records_terminal(tmp_path, body, mime, expected):
    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            self.send_response(200); self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body))); self.end_headers()
            for i in range(0, len(body), 3):
                self.wfile.write(body[i:i+3]); self.wfile.flush()
    upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
    log = tmp_path / 'events.jsonl'
    relay = make_server('127.0.0.1', 0, f'http://127.0.0.1:{upstream.server_port}/v1',
                        'test-secret', log, client_token='test-client', actor_mcp_only=True)
    threads = [threading.Thread(target=x.serve_forever, daemon=True) for x in (upstream, relay)]
    for thread in threads: thread.start()
    try:
        tools = [{'type':'namespace','name':'mcp__desktop','tools':[{'type':'function','name':'screenshot'}]},
                 {'type':'namespace','name':'mcp__collaboration','tools':[{'type':'function','name':'send_message'}]}]
        response = requests.post(f'http://127.0.0.1:{relay.server_port}/actor/A/v1/responses',
            json={'model':'test','tools':tools}, headers={'Authorization':'Bearer test-client'}, timeout=5)
        assert response.status_code == 200 and response.content == body
        event = json.loads(log.read_text())
        assert event['response_terminal'] == expected
        assert 'test-secret' not in log.read_text() and body.decode() not in log.read_text()
    finally:
        for server in (relay, upstream): server.shutdown(); server.server_close()
        for thread in threads: thread.join(timeout=5)


def test_health_get_is_not_model_relay_event(tmp_path):
    log = tmp_path / 'events.jsonl'
    relay = make_server('127.0.0.1', 0, 'http://127.0.0.1:9/v1',
                        'test-secret', log, client_token='test-client')
    thread = threading.Thread(target=relay.serve_forever, daemon=True); thread.start()
    try:
        response = requests.get(f'http://127.0.0.1:{relay.server_port}/health', timeout=5)
        assert response.status_code == 200 and not log.exists()
    finally:
        relay.shutdown(); relay.server_close(); thread.join(timeout=5)


def test_oversized_frame_is_unverifiable():
    evidence = ResponseEvidence('text/event-stream')
    evidence.LIMIT = 8
    evidence.feed(b'data: ' + b'x'*20)
    assert evidence.finish()['response_terminal'] == 'malformed'
