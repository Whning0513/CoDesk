"""Small, preplanned image+function SSE probe; never save keys or model content."""

import argparse
import base64
from collections import Counter
import io
import json
from pathlib import Path
import re
import time

from PIL import Image
import requests


ENDPOINTS = {'haogpt': 'https://api.haogpt.net/v1', 'docode': 'https://docode.cc/v1'}
ORDER = ('haogpt', 'docode', 'docode', 'haogpt')


def probe(label, endpoint, key, payload, read_timeout=90, wall_deadline=125):
    started = time.monotonic()
    result = {'endpoint': label, 'model': 'gpt-6-astra', 'http_status': None,
              'completed_event': False, 'function_call_seen': False, 'first_event_s': None,
              'event_count': 0, 'error_type': None, 'usage': None, 'reported_model': None}
    response = None
    try:
        response = requests.post(endpoint.rstrip('/') + '/responses', json=payload,
                                 headers={'Authorization': 'Bearer ' + key},
                                 stream=True, timeout=(10, read_timeout))
        result['http_status'] = response.status_code
        if response.status_code != 200:
            return result
        for line in response.iter_lines(decode_unicode=True):
            if time.monotonic() - started > wall_deadline:
                result['error_type'] = 'WallDeadlineExceeded'
                break
            if isinstance(line, bytes):
                line = line.decode('utf-8', errors='replace')
            if not line or not line.startswith('data:'):
                continue
            data = line[5:].strip()
            if data == '[DONE]':
                break
            try:
                event = json.loads(data)
            except ValueError:
                result['error_type'] = 'InvalidSSEJson'
                break
            result['event_count'] += 1
            if result['first_event_s'] is None:
                result['first_event_s'] = round(time.monotonic() - started, 3)
            kind = event.get('type')
            item = event.get('item') or {}
            if kind == 'response.output_item.done' and item.get('type') == 'function_call':
                result['function_call_seen'] |= item.get('name') == 'report_visible'
            if kind == 'response.completed':
                info = event.get('response') or {}
                result['completed_event'] = info.get('status') == 'completed'
                reported = info.get('model')
                if isinstance(reported, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', reported):
                    result['reported_model'] = reported
                usage = info.get('usage') or {}
                result['usage'] = {key: usage[key] for key in ('input_tokens', 'output_tokens', 'total_tokens')
                                   if isinstance(usage.get(key), int)}
                result['function_call_seen'] |= any(
                    x.get('type') == 'function_call' and x.get('name') == 'report_visible'
                    for x in (info.get('output') or []) if isinstance(x, dict))
            if kind in ('error', 'response.failed'):
                result['error_type'] = kind
                break
    except requests.RequestException as exc:
        result['error_type'] = type(exc).__name__
    finally:
        if response is not None:
            response.close()
        result['elapsed_s'] = round(time.monotonic() - started, 3)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--key-file', type=Path, required=True)
    parser.add_argument('--screenshot', type=Path, required=True)
    args = parser.parse_args()
    root = args.run_root.resolve()
    if not root.name.startswith('case5-endpoint-probe-'):
        raise ValueError('invalid run_id prefix')
    root.mkdir(parents=True, exist_ok=False)
    key = args.key_file.read_text().strip()
    if not key:
        raise ValueError('credential file is empty')
    with Image.open(args.screenshot) as original:
        img = original.convert('RGB')
        img.thumbnail((640, 360))
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
    payload = {
        'model': 'gpt-6-astra', 'reasoning': {'effort': 'medium'}, 'stream': True,
        'input': [{'role': 'user', 'content': [
            {'type': 'input_text', 'text': 'Call report_visible with a short description of the desktop.'},
            {'type': 'input_image', 'image_url': 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()},
        ]}],
        'tools': [{'type': 'function', 'name': 'report_visible', 'description': 'Describe the desktop',
                   'parameters': {'type': 'object', 'properties': {'description': {'type': 'string'}},
                                  'required': ['description'], 'additionalProperties': False}}],
        'tool_choice': {'type': 'function', 'name': 'report_visible'}, 'max_output_tokens': 150,
    }
    results = []
    for number, label in enumerate(ORDER, 1):
        row = {'attempt': number, **probe(label, ENDPOINTS[label], key, payload)}
        results.append(row)
        with (root / 'attempts.jsonl').open('a') as stream:
            stream.write(json.dumps(row, sort_keys=True) + '\n')
    summary = {}
    for label in ENDPOINTS:
        rows = [r for r in results if r['endpoint'] == label]
        summary[label] = {'attempts': len(rows),
                          'http_status_counts': dict(Counter(str(r['http_status']) for r in rows)),
                          'completed_streams': sum(r['completed_event'] for r in rows),
                          'function_calls': sum(r['function_call_seen'] for r in rows),
                          'reported_models': dict(Counter(str(r['reported_model']) for r in rows)),
                          'interruptions': sum(not r['completed_event'] for r in rows),
                          'elapsed_s': [r['elapsed_s'] for r in rows]}
    (root / 'summary.json').write_text(json.dumps({'order': ORDER, 'results': summary}, indent=2) + '\n')
    print(json.dumps(summary, sort_keys=True))


if __name__ == '__main__':
    main()
