import io
from concurrent.futures import ThreadPoolExecutor

from app.manifest import canonical, digest
from app.modules.archive.service import sample_plan, seed


def publish(client, run, legs):
    return client.post('/api/dispatch/publish', json={'expected': run, 'legs': legs})


def test_workbench_and_seven_read_entries(client, run_id):
    page = client.get('/')
    assert page.status_code == 200 and '潮汐槽位图' in page.get_data(as_text=True)
    for stage in ('intake', 'capacity', 'replay', 'demand', 'dispatch', 'inventory'):
        res = client.get(f'/api/{stage}?run={run_id}')
        assert res.status_code == 200 and res.json['id'] == run_id and res.json['data']
    res = client.get('/api/runs')
    assert res.status_code == 200 and res.json['history'][0]['id'] == run_id


def test_seed_and_rerun_preserve_id_export_and_history(client, run_id, app):
    export = f'/api/runs/{run_id}/evidence.json'
    original = client.get(export).data
    seed(app.extensions['shift_store'])
    for _ in range(2):
        response = client.post('/api/runs/rerun', json={'expected': run_id})
        assert response.json == {'id': run_id, 'created': False, 'changed': False}
    assert client.get(export).data == original
    assert len(client.get('/api/runs').json['history']) == 1


def test_export_has_integrity_and_traceable_event_evidence(client, run_id, sources):
    response = client.get(f'/api/runs/{run_id}/evidence.json')
    output = response.json['evidence']
    assert response.headers['Content-Disposition'].startswith('attachment;')
    assert response.json['evidence_sha256'] == digest(canonical(output).encode())
    assert output['manifest']['inputs']['events']['sha256'] == digest(sources['events'])
    assert output['dispatch']['comparison']['changes'][0]['line'] == 6
    assert output['intake']['excluded'][0]['code'] == 'REPEATED_HEADER'
    assert output['inventory']['plan']['end_fleet'] == 33


def test_successful_upload_can_be_replayed_from_archived_bytes(client, run_id, sources):
    raw = sources['events'].replace('重发'.encode(), '同笔补传'.encode())
    response = client.post('/api/intake', data={'expected': run_id, 'events': (io.BytesIO(raw), 'new.csv')})
    new = response.json['id']
    assert response.json['created'] is True and run_id != new
    assert client.get('/api/runs').json['manifest']['inputs']['events']['sha256'] == digest(raw)
    assert client.post('/api/runs/rerun', json={'expected': new}).json['id'] == new
    assert [row['id'] for row in client.get('/api/runs').json['history']] == [new, run_id]


def test_failed_unload_leaves_no_published_partial_load(client, run_id, app):
    leg = dict(sample_plan()[0], id='M-02', to='001', **{'from': '003', 'truck': 'T-02', 'depart': '2026-11-20T09:38:00+08:00', 'arrive': '2026-11-20T09:43:00+08:00', 'count': 3})
    route = dict(sample_plan()[0], to='003', depart='2026-11-20T08:24:00+08:00', arrive='2026-11-20T08:30:00+08:00', count=1)
    response = publish(client, run_id, [route, leg])
    assert response.status_code == 422 and response.json['code'] == 'DROP_FULL'
    db = app.extensions['shift_store']
    with db.connect() as conn:
        assert conn.execute('SELECT count(*) FROM runs').fetchone() == (1,)
        assert conn.execute('SELECT count(*) FROM sources').fetchone() == (3,)
    assert client.get('/health').json['run'] == run_id


# TRAP-26
def test_stale_publish_rejected_and_archive_can_be_restored(client, run_id):
    new = publish(client, run_id, []).json['id']
    stale = publish(client, run_id, [sample_plan()[0]])
    assert stale.status_code == 409 and stale.json['details']['current'] == new
    assert client.get(f'/api/runs?run={run_id}').json['manifest']['id'] == run_id
    response = client.post('/api/runs/restore', json={'target': run_id, 'expected': new})
    assert response.json == {'id': run_id, 'created': False, 'changed': True}
    assert len(client.get('/api/runs').json['history']) == 2


def test_concurrent_equal_publish_yields_one_new_record(app, run_id):
    def submit(_):
        return publish(app.test_client(), run_id, []).json
    with ThreadPoolExecutor(2) as workers:
        one, two = workers.map(submit, range(2))
    assert one['id'] == two['id'] and sorted([one['created'], two['created']]) == [False, True]
    assert len(app.test_client().get('/api/runs').json['history']) == 2


def test_storage_failure_rolls_back_sources_and_new_snapshot(app, client, run_id):
    db = app.extensions['shift_store']
    with db.connect() as conn:
        conn.execute("CREATE TRIGGER stop_active BEFORE UPDATE ON active BEGIN SELECT RAISE(ABORT, 'test'); END")
    response = publish(client, run_id, [])
    assert (response.status_code, response.json['code']) == (503, 'STORE_UNAVAILABLE')
    with db.connect() as conn:
        assert conn.execute('SELECT count(*) FROM runs').fetchone() == (1,)
        assert conn.execute('SELECT count(*) FROM sources').fetchone() == (3,)
    assert db.active() == run_id


def test_unknown_run_and_bad_shape_have_recoverable_errors(client, run_id):
    missing = client.get('/api/runs/unknown/evidence.json')
    assert (missing.status_code, missing.json['code']) == (404, 'RUN_NOT_FOUND')
    bad = client.post('/api/dispatch/preview', json={'run': run_id, 'legs': [{}]})
    assert (bad.status_code, bad.json['code']) == (422, 'BAD_PLAN')
