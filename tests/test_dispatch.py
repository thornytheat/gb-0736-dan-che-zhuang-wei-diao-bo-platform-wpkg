from app.modules.archive.service import sample_plan


def try_plan(client, run_id, legs):
    return client.post('/api/dispatch/preview', json={'run': run_id, 'legs': legs})


def test_balanced_delta_reports_harm_as_well_as_recovered(snapshot):
    result = snapshot['dispatch']['comparison']
    assert (result['before'], result['after'], result['delta'], result['recovered'], result['newly_missed']) == (11, 8, -3, 4, 1)
    lost = result['changes'][-1]
    assert (lost['id'], lost['before'], lost['after']) == ('0036', None, 'NO_BIKE')


def test_overweight_route_has_structured_failure(client, run_id):
    leg = dict(sample_plan()[0], count=5)
    response = try_plan(client, run_id, [leg])
    assert (response.status_code, response.json['code'], response.json['details']['available']) == (422, 'TRUCK_LOAD', 4)


def test_before_truck_is_available(client, run_id):
    leg = dict(sample_plan()[0], depart='2026-11-20T08:05:00+08:00')
    response = try_plan(client, run_id, [leg])
    assert response.json['code'] == 'TRUCK_OVERLAP'
    assert response.json['details']['available_at'] == '2026-11-20T00:06:00Z'


def test_successive_truck_moves_must_connect(client, run_id):
    first = sample_plan()[0]
    second = dict(first, id='N', depart='2026-11-20T08:15:00+08:00', arrive='2026-11-20T08:22:00+08:00')
    response = try_plan(client, run_id, [first, second])
    assert (response.json['code'], response.json['details']['station']) == ('TRUCK_POSITION', '002')


def test_arrival_checks_capacity_at_actual_time(client, run_id):
    leg = dict(sample_plan()[0], to='003', depart='2026-11-20T08:24:00+08:00', arrive='2026-11-20T08:30:00+08:00', count=1)
    response = try_plan(client, run_id, [leg])
    assert response.status_code == 422
    assert response.json['code'] == 'DROP_FULL'
    assert response.json['details'] == {'leg': 'M-01', 'station': '003', 'at': '2026-11-20T00:30:00Z',
                                        'available': 0, 'requested': 1, 'version_line': 6}


def test_pickup_uses_docked_stock_and_reports_exact_shortage(client, run_id):
    leg = dict(sample_plan()[1], depart='2026-11-20T09:22:00+08:00', arrive='2026-11-20T09:30:00+08:00', count=3)
    response = try_plan(client, run_id, [leg])
    assert (response.json['code'], response.json['details']['available']) == ('PICKUP_SHORT', 1)


def test_departure_and_arrival_within_work_shift(client, run_id):
    leg = dict(sample_plan()[0], arrive='2026-11-20T10:00:00+08:00')
    response = try_plan(client, run_id, [leg])
    assert (response.status_code, response.json['code']) == (422, 'OUTSIDE_SHIFT')


def test_minimum_travel_time_and_zero_delta_plan(client, run_id):
    leg = dict(sample_plan()[0], arrive='2026-11-20T08:12:59+08:00')
    assert try_plan(client, run_id, [leg]).json['code'] == 'TRAVEL_TIME'
    empty = try_plan(client, run_id, []).json['dispatch']['comparison']
    assert (empty['before'], empty['after'], empty['delta'], empty['changes']) == (11, 11, 0, [])


def test_arrival_allows_immediate_next_leg_on_same_truck(client, run_id):
    first = sample_plan()[0]
    second = dict(first, id='N', count=1, **{'from': '002', 'to': '004', 'depart': first['arrive'], 'arrive': '2026-11-20T08:36:00+08:00'})
    response = try_plan(client, run_id, [second, first])
    assert response.status_code == 200
    result = response.json['dispatch']
    assert [leg['id'] for leg in result['legs']] == ['M-01', 'N']
    movements = [row['kind'] for row in result['movements'] if row['at'] == '2026-11-20T00:14:00Z']
    assert movements == ['unload', 'load']
