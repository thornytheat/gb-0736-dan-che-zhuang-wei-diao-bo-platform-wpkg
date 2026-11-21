from dataclasses import replace

from app.modules.replay.service import replay


def find(result, event):
    return next(row for row in result['timeline'] if row['id'] == event and row['kind'] in {'rent', 'return'})


# TRAP-13
def test_physical_order_beats_file_or_received_order(snapshot):
    baseline = snapshot['replay']['base']
    late = find(baseline, '0011')
    rent = find(baseline, '0012')
    assert late['after']['docked'] == 1 and late['late']
    assert rent['code'] is None and rent['before']['docked'] == 1


def test_failed_attempts_do_not_change_inventory(snapshot):
    row = find(snapshot['replay']['base'], '0005')
    assert row['code'] == 'NO_DOCK' and row['before'] == row['after'] and row['after']['docked'] == 10


# TRAP-19
def test_same_clock_arrival_before_attempt(snapshot):
    result = snapshot['replay']['plan']
    event = find(result, '0008')
    index = result['timeline'].index(event)
    unload = result['timeline'][index - 1]
    assert unload['at'] == event['at'] and unload['kind'] == 'unload'
    assert event['code'] is None and event['after']['docked'] == 2


def test_closure_moves_into_holding_before_rent(snapshot):
    timeline = snapshot['replay']['base']['timeline']
    row = find(snapshot['replay']['base'], '0018')
    closed = timeline[timeline.index(row) - 1]
    assert closed['kind'] == 'capacity' and closed['at'] == row['at']
    assert (row['after']['docked'], row['after']['held'], row['code']) == (0, 7, 'STATION_CLOSED')


def test_reopening_and_borrowing_reseat_held_bicycles(snapshot):
    row = find(snapshot['replay']['base'], '0020')
    assert (row['before']['held'], row['after']['held'], row['after']['docked'], row['after']['capacity']) == (4, 3, 3, 3)


def test_rider_pool_cannot_go_below_zero(snapshot, shift):
    first = snapshot['intake']['events'][0]
    result = replay(replace(shift, opening_road=0), [first], snapshot['capacity']['segments'])
    denied = find(result, '0001')
    assert denied['code'] == 'NO_ROAD_BIKE' and denied['road'] == 0 and denied['after']['docked'] == 8


def test_equal_times_resolve_by_opaque_id(snapshot, shift):
    at = '2026-11-20T00:00:30Z'
    attempts = [{'id': key, 'station': '002', 'kind': 'rent', 'at': at} for key in ('03','02','01')]
    output = replay(shift, attempts, snapshot['capacity']['segments'])
    assert [(find(output, key)['id'], find(output, key)['code']) for key in ('01','02','03')] == [
        ('01', None), ('02', None), ('03', 'NO_BIKE')]
