"""Versioned, fail-closed review of transient save-validation retries."""
import hashlib
import json

EXPECTED = 'RuntimeError: artifact changed during save; retry after saving completes'


def review(root, errors, condition):
    if not errors:
        return True
    if len(errors) > 3 or any(e != EXPECTED for e in errors):
        return False
    try:
        rows = [json.loads(x) for x in (root / 'workspace_versions/events.jsonl').read_text().splitlines()]
        retries = [r for r in rows if r.get('event') == 'save_validation_retry']
        faults = [r for r in rows if r.get('event') == 'sync_error']
        recovered = [r for r in rows if r.get('event') == 'save_validation_recovered']
        if len(retries) != len(errors) or len(faults) != len(errors) or len(recovered) != len(errors):
            return False
        if len({r['retry_id'] for r in retries}) != len(retries):
            return False
        for retry, fault in zip(retries, faults):
            found = [r for r in recovered if r.get('retry_id') == retry['retry_id']]
            if len(found) != 1:
                return False
            done = found[0]
            if any(fault.get(k) != retry.get(k) for k in ('retry_id', 'actor', 'guest_path')):
                return False
            if fault.get('error') != EXPECTED or not (retry['time'] <= fault['time'] <= done['time'] <= retry['time'] + 60):
                return False
            if any(done.get(k) != retry.get(k) for k in ('actor', 'guest_path')):
                return False
            if done['actor'] not in ('A', 'B') or done.get('peer_sha256') != done.get('sha256'):
                return False
            versions = [r for r in rows if r.get('event') == 'revision_saved' and r.get('actor') == done['actor'] and r.get('revision') == done['revision'] and r.get('sha256') == done['sha256'] and r.get('guest_path') == done['guest_path'] and r['time'] <= done['time']]
            if len(versions) != 1:
                return False
            v = versions[0]
            path = (root / 'workspace_versions' / v['file']).resolve()
            path.relative_to((root / 'workspace_versions').resolve())
            if hashlib.sha256(path.read_bytes()).hexdigest() != done['sha256'] or path.stat().st_size != done['bytes']:
                return False
            if condition.endswith('isolated'):
                transfer = [r for r in rows if r.get('event') == 'transfer_verified' and r.get('actor') == done['actor'] and r.get('revision') == done['revision'] and r.get('sha256') == done['sha256'] and r.get('guest_path') == done['guest_path'] and r.get('destination_guest') == done['destination_guest'] and r['time'] <= done['time']]
                if len(transfer) != 1 or not done['distinct_guest']:
                    return False
            elif done['distinct_guest']:
                return False
        return True
    except (OSError, KeyError, ValueError, TypeError):
        return False
