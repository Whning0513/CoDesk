import hashlib
import json

import pytest
from oscombo.collab.data_to_deck.case5_save_retry_review import EXPECTED, review


def evidence(root):
    base = root / 'workspace_versions'
    (base / 'A').mkdir(parents=True)
    data = b'stable scene'
    (base / 'A/revision-000001.blend').write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    common = dict(actor='A', guest_path='/task/A.blend')
    rows = [dict(event='save_validation_retry', retry_id='r1', time=10, **common),
            dict(event='sync_error', error=EXPECTED, retry_id='r1', time=11, **common),
            dict(event='revision_saved', revision=1, sha256=sha, file='A/revision-000001.blend', time=12, **common),
            dict(event='transfer_verified', revision=1, sha256=sha, destination_guest='B', time=13, **common),
            dict(event='save_validation_recovered', retry_id='r1', revision=1, sha256=sha, peer_sha256=sha, bytes=len(data), destination_guest='B', distinct_guest=True, time=14, **common)]
    return base, rows


def save(base, rows):
    (base / 'events.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))


def test_review_proves_recovered_transfer(tmp_path):
    base, rows = evidence(tmp_path); save(base, rows)
    assert review(tmp_path, [EXPECTED], 'collaborative_isolated')


@pytest.mark.parametrize('mutation', ['no_actor', 'wrong_actor', 'wrong_path', 'late', 'wrong_hash', 'missing_transfer', 'extra_fault', 'legacy'])
def test_review_fails_closed(tmp_path, mutation):
    base, rows = evidence(tmp_path)
    if mutation == 'no_actor': del rows[0]['actor']
    if mutation == 'wrong_actor': rows[-1]['actor'] = 'B'
    if mutation == 'wrong_path': rows[-1]['guest_path'] = '/task/B.blend'
    if mutation == 'late': rows[-1]['time'] = 71
    if mutation == 'wrong_hash': rows[-1]['peer_sha256'] = '0'*64
    if mutation == 'missing_transfer': rows.pop(3)
    if mutation == 'extra_fault': rows.append(dict(event='sync_error', error='bad', time=15))
    if mutation == 'legacy': rows.pop(0)
    save(base, rows)
    assert not review(tmp_path, [EXPECTED], 'collaborative_isolated')
