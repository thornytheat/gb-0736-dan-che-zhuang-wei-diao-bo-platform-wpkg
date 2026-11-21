import io
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.config import SAMPLES

AS_OF_PARTIAL = '2026-11-20T08:55:00+08:00'
AS_OF_FULL = '2026-11-20T08:59:00+08:00'


def ingest(client, batch_id, station, covered_until, raw):
    return client.post('/api/bulletin/backfill',
                       data={'batch_id': batch_id, 'station': station, 'covered_until': covered_until,
                             'events': (io.BytesIO(raw), 'batch.csv')})


def ingest_sample(client, name):
    meta = {item['batch_id']: item for item in json.loads((SAMPLES / 'backfill' / 'batches.json').read_bytes())}[name]
    return ingest(client, name, meta['station'], meta['covered_until'],
                  (SAMPLES / 'backfill' / meta['file']).read_bytes())


def publish(client, expected, as_of, mode):
    return client.post('/api/bulletin/publish', json={'expected': expected, 'as_of': as_of, 'mode': mode})


def stations(payload):
    return {row['station']: row for row in payload['stations']}


@pytest.fixture
def two_batches(client):
    ingest_sample(client, 'BF-002A')
    ingest_sample(client, 'BF-001A')


@pytest.fixture
def partial(client, two_batches):
    return publish(client, None, AS_OF_PARTIAL, 'partial').json['id']


@pytest.fixture
def full(client, partial):
    for name in ('BF-003A', 'BF-004A', 'BF-002B', 'BF-001B'):
        ingest_sample(client, name)
    return publish(client, partial, AS_OF_FULL, 'all').json['id']


def test_draft_marks_unconfirmed_stations_with_reasons(client):
    view = client.get('/api/bulletin').json
    assert view['active'] is None
    assert view['draft']['totals']['confirmed'] == 0 and view['draft']['totals']['carried'] == 4
    for row in view['draft']['stations']:
        assert row['status'] == 'carried' and row['reason'] == 'NO_BACKFILL' and row['cutoff'] is None
    ingest_sample(client, 'BF-002A')
    view = client.get('/api/bulletin?as_of=2026-11-20T08%3A58%3A00%2B08%3A00').json
    state = stations(view['draft'])
    assert state['002']['status'] == 'carried' and state['002']['reason'] == 'CUTOFF_SHORT'
    assert state['002']['reported_until'] == '2026-11-20T00:55:00Z'
    assert state['001']['reason'] == 'NO_BACKFILL'


def test_batch_ingest_idempotent_conflict_rejected_and_raw_kept(client, app):
    raw = (SAMPLES / 'backfill' / '002.csv').read_bytes()
    first = ingest_sample(client, 'BF-002A')
    assert first.json['created'] is True and first.json['accepted'] == 3
    again = ingest_sample(client, 'BF-002A')
    assert again.json['created'] is False and again.json['accepted'] == 3
    changed = ingest(client, 'BF-002A', '002', '2026-11-20T08:55:00+08:00', raw.replace(b'0101', b'9999', 1))
    assert changed.status_code == 409 and changed.json['code'] == 'BATCH_CONFLICT'
    db = app.extensions['shift_store']
    with db.connect() as conn:
        assert conn.execute('SELECT count(*) FROM backfill_batches').fetchone() == (1,)
        stored = conn.execute('SELECT raw FROM backfill_batches WHERE id = ?', ('BF-002A',)).fetchone()
        assert bytes(stored[0]) == raw
        assert conn.execute('SELECT count(*) FROM backfill_events').fetchone() == (3,)


def test_batch_events_quarantined_with_reasons_and_never_merged(client):
    raw = ('event_id,station,kind,occurred_at,received_at,note\n'
           '0201,001,return,2026-11-20T08:40:00+08:00,2026-11-20T09:10:00+08:00,他站事件\n'
           '0202,002,return,2026-11-20T08:56:00+08:00,2026-11-20T09:10:00+08:00,超出覆盖\n'
           '0203,002,return,2026-11-20T08:50:00+08:00,2026-11-20T09:10:00+08:00,正常补传\n').encode()
    response = ingest(client, 'BF-X01', '002', '2026-11-20T08:55:00+08:00', raw)
    assert response.json['accepted'] == 1 and response.json['quarantined'] == 2
    assert response.json['reasons'] == {'FOREIGN_STATION': 1, 'BEYOND_COVERAGE': 1}
    view = client.get('/api/bulletin').json
    batch = view['batches'][0]
    assert [row['code'] for row in batch['excluded']] == ['FOREIGN_STATION', 'BEYOND_COVERAGE']
    assert view['draft']['totals']['events'] == 50 + 1


def test_conflicting_event_id_across_sources_is_visible_and_excluded(client):
    raw = ('event_id,station,kind,occurred_at,received_at,note\n'
           '0008,002,return,2026-11-20T08:14:00+08:00,2026-11-20T09:10:00+08:00,同号异义\n').encode()
    ingest(client, 'BF-X02', '002', '2026-11-20T08:55:00+08:00', raw)
    view = client.get('/api/bulletin').json
    assert view['draft']['conflicts'] == [{'id': '0008', 'rows': 2, 'sources': ['BF-X02', 'base']}]
    assert view['draft']['totals']['events'] == 49


def test_partial_publish_carries_unconfirmed_at_previous_values(client, partial):
    active = client.get('/api/bulletin').json['active']
    assert active['manifest']['id'] == partial and active['manifest']['mode'] == 'partial'
    state = stations(active)
    assert state['001']['status'] == 'confirmed' and state['001']['cutoff'] == '2026-11-20T00:55:00Z'
    assert state['002']['available'] == 1 and state['002']['missed_rent'] == 0
    for code in ('003', '004'):
        assert state[code]['status'] == 'carried' and state[code]['reason'] == 'NO_BACKFILL'
        assert state[code]['cutoff'] is None and state[code]['carried_from'] is None
    flips = {row['id']: row for row in active['changes']['attempts']}
    assert flips['0006'] == {'after': None, 'at': '2026-11-20T00:10:00Z', 'before': 'NO_BIKE',
                             'id': '0006', 'kind': 'rent', 'station': '002'}
    assert [row['id'] for row in active['changes']['introduced']] == ['0101', '0102', '0103']
    diff = {row['station']: row for row in active['changes']['stations']}
    assert (diff['002']['before_available'], diff['002']['after_available']) == (0, 1)
    assert (diff['002']['before_missed'], diff['002']['after_missed']) == (1, 0)
    assert active['changes']['vs'] == 'base'


def test_all_mode_switch_is_atomic_when_stations_pending(client, two_batches, app):
    response = publish(client, None, AS_OF_PARTIAL, 'all')
    assert response.status_code == 409 and response.json['code'] == 'STATIONS_PENDING'
    assert response.json['details']['stations'] == [{'station': '003', 'reason': 'NO_BACKFILL'},
                                                    {'station': '004', 'reason': 'NO_BACKFILL'}]
    db = app.extensions['shift_store']
    with db.connect() as conn:
        assert conn.execute('SELECT count(*) FROM bulletins').fetchone() == (0,)
        assert conn.execute('SELECT count(*) FROM bulletin_active').fetchone() == (0,)
    assert client.get('/api/bulletin').json['active'] is None


def test_partial_publish_requires_at_least_one_confirmed(client):
    response = publish(client, None, AS_OF_PARTIAL, 'partial')
    assert response.status_code == 409 and response.json['code'] == 'STATIONS_PENDING'


def test_retry_same_backfill_never_creates_second_bulletin(client, partial, app):
    before = client.get('/api/bulletin').json['history']
    assert ingest_sample(client, 'BF-002A').json['created'] is False
    retry = publish(client, partial, AS_OF_PARTIAL, 'partial')
    assert retry.json == {'id': partial, 'created': False, 'changed': False}
    db = app.extensions['shift_store']
    with db.connect() as conn:
        assert conn.execute('SELECT count(*) FROM bulletins').fetchone() == (1,)
    assert client.get('/api/bulletin').json['history'] == before


def test_full_switch_after_all_stations_confirmed(client, partial, full):
    active = client.get('/api/bulletin').json['active']
    assert active['manifest']['id'] == full and full != partial
    assert active['manifest']['mode'] == 'all' and active['manifest']['previous'] == partial
    assert active['manifest']['as_of'] == '2026-11-20T00:59:00Z'
    for row in active['stations']:
        assert row['status'] == 'confirmed' and row['cutoff'] == '2026-11-20T00:59:00Z'
    state = stations(active)
    assert state['003']['missed_return'] == 3 and state['003']['held'] == 1
    assert [row['id'] for row in active['changes']['introduced']] == ['0101', '0102', '0103', '0105', '0106', '0104']
    assert active['changes']['vs'] == partial
    history = client.get('/api/bulletin').json['history']
    assert [row['id'] for row in history] == [full, partial]
    assert [bool(row['active']) for row in history] == [True, False]


def test_publish_with_stale_expected_is_rejected(client, partial):
    same = publish(client, 'f' * 64, AS_OF_PARTIAL, 'partial')
    assert same.json == {'id': partial, 'created': False, 'changed': True}
    ingest_sample(client, 'BF-003A')
    response = publish(client, 'f' * 64, AS_OF_PARTIAL, 'partial')
    assert response.status_code == 409 and response.json['code'] == 'STALE_BULLETIN'
    assert response.json['details']['current'] == partial


def test_concurrent_identical_publish_yields_one_bulletin(app, client, two_batches):
    def submit(_):
        return publish(app.test_client(), None, AS_OF_PARTIAL, 'partial').json
    with ThreadPoolExecutor(2) as workers:
        one, two = workers.map(submit, range(2))
    assert one['id'] == two['id'] and sorted([one['created'], two['created']]) == [False, True]
    assert len(client.get('/api/bulletin').json['history']) == 1


def test_storage_failure_rolls_back_bulletin_and_keeps_active(client, partial, app):
    db = app.extensions['shift_store']
    with db.connect() as conn:
        conn.execute("CREATE TRIGGER stop_bulletin BEFORE UPDATE ON bulletin_active "
                     "BEGIN SELECT RAISE(ABORT, 'test'); END")
    ingest_sample(client, 'BF-003A')
    response = publish(client, partial, AS_OF_PARTIAL, 'partial')
    assert response.status_code == 503 and response.json['code'] == 'STORE_UNAVAILABLE'
    with db.connect() as conn:
        assert conn.execute('SELECT count(*) FROM bulletins').fetchone() == (1,)
        assert conn.execute('SELECT bulletin_id FROM bulletin_active').fetchone() == (partial,)
    assert client.get('/api/bulletin').json['active']['manifest']['id'] == partial


def test_verify_recomputes_from_sealed_inputs(client, full, partial):
    for bulletin_id in (partial, full):
        assert client.post('/api/bulletin/verify', json={'id': bulletin_id}).json == {'id': bulletin_id, 'ok': True}
    missing = client.post('/api/bulletin/verify', json={'id': 'unknown'})
    assert missing.status_code == 404 and missing.json['code'] == 'BULLETIN_NOT_FOUND'


def test_verify_ignores_batches_that_arrived_later(client, partial):
    ingest_sample(client, 'BF-003A')
    assert client.post('/api/bulletin/verify', json={'id': partial}).json == {'id': partial, 'ok': True}


def test_evidence_download_carries_inputs_and_reason_labels(client, full, sources):
    response = client.get(f'/api/bulletin/{full}/evidence.json')
    assert response.headers['Content-Disposition'].startswith('attachment;')
    evidence = response.json['evidence']
    assert evidence['manifest']['inputs']['batches'].keys() == {'BF-002A', 'BF-001A', 'BF-003A', 'BF-004A', 'BF-002B', 'BF-001B'}
    assert evidence['reason_labels']['NO_BACKFILL'] == '终端尚未回传'
    assert evidence['manifest']['run'] == client.get('/api/runs').json['manifest']['id']


def test_run_switch_starts_fresh_chain_and_keeps_old_bulletin(client, partial, sources, run_id):
    raw = sources['events'].replace('重发'.encode(), '换班标记'.encode())
    response = client.post('/api/intake', data={'expected': run_id, 'events': (io.BytesIO(raw), 'new.csv')})
    new_run = response.json['id']
    assert new_run != run_id
    view = client.get('/api/bulletin').json
    assert view['active']['manifest']['id'] == partial and view['active']['manifest']['run'] == run_id
    assert view['draft']['manifest']['previous'] == 'base' and view['draft']['manifest']['run'] == new_run
    assert view['batches'] == []
    assert client.post('/api/bulletin/verify', json={'id': partial}).json == {'id': partial, 'ok': True}
    ingest_sample(client, 'BF-002A')
    moved = publish(client, partial, AS_OF_PARTIAL, 'partial')
    assert moved.json['created'] is True and moved.json['changed'] is True
    active = client.get('/api/bulletin').json['active']
    assert active['manifest']['run'] == new_run and active['manifest']['previous'] == 'base'


def test_bad_batch_requests_have_recoverable_errors(client):
    assert ingest(client, '坏批次', '002', '2026-11-20T08:55:00+08:00', b'x').json['code'] == 'BAD_BATCH'
    assert ingest(client, 'BF-OK', '009', '2026-11-20T08:55:00+08:00', b'x').json['code'] == 'UNKNOWN_STATION'
    assert ingest(client, 'BF-OK', '002', '2026-11-20T11:00:00+08:00', b'x').json['code'] == 'OUTSIDE_SHIFT'
    assert client.post('/api/bulletin/publish', json={'expected': None, 'as_of': AS_OF_PARTIAL}).json['code'] == 'BAD_REQUEST'
    assert client.post('/api/bulletin/publish',
                       json={'expected': None, 'as_of': AS_OF_PARTIAL, 'mode': 'all'}).json['code'] == 'STATIONS_PENDING'
    empty = client.post('/api/bulletin/backfill', data={'batch_id': 'BF-E', 'station': '002',
                                                        'covered_until': '2026-11-20T08:55:00+08:00'})
    assert empty.json['code'] == 'UPLOAD_REQUIRED'
    assert client.delete('/api/bulletin/backfill').status_code == 405
