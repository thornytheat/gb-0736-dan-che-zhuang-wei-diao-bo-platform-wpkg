from copy import deepcopy

from app.modules.inventory.service import reconcile


def test_station_ledger_accounts_for_transfers(snapshot):
    row = snapshot['inventory']['plan']['stations'][0]
    assert (row['opening'], row['return'], row['unload'], row['rent'], row['load'], row['closing'], row['gap']) == (8, 7, 2, 6, 3, 8, 0)


def test_fleet_is_constant_including_in_transit_and_holding(snapshot, shift):
    stations = {code: config['opening'] for code, config in shift.stations.items()}
    for row in snapshot['replay']['plan']['timeline']:
        state = row['after']
        stations[row['station']] = state['docked'] + state['held']
        assert sum(stations.values()) + row['road'] + row['transit'] == 33
        assert 0 <= state['docked'] <= state['capacity'] and state['held'] >= 0


def test_end_pool_excludes_temporary_truck_stock(snapshot):
    audit = snapshot['inventory']['plan']
    assert (audit['road_opening'], audit['road_end'], audit['in_transit_end'], audit['move_gap']) == (14, 20, 0, 0)


def test_receipts_capacity_and_failed_demand_reconcile(snapshot):
    audit = snapshot['inventory']['base']
    assert snapshot['intake']['input_rows'] == 50 + 11
    assert snapshot['capacity']['input_rows'] == 7 + 3
    assert (audit['intake_gap'], audit['capacity_gap'], audit['attempt_gap']) == (0, 0, 0)


def test_tampered_closing_reports_exact_gap(snapshot, shift):
    result = deepcopy(snapshot['replay']['plan'])
    result['closing']['002']['docked'] += 1
    check = reconcile(shift, result, snapshot['intake'], snapshot['capacity'])
    assert check['ok'] is False and check['fleet_gap'] == 1 and check['stations'][1]['gap'] == 1


def test_invalid_intermediate_dock_and_unbalanced_lorry_are_detected(snapshot, shift):
    result = deepcopy(snapshot['replay']['plan'])
    result['timeline'][0]['after']['docked'] = 11
    result['transit'] = 1
    check = reconcile(shift, result, snapshot['intake'], snapshot['capacity'])
    assert check['ok'] is False and check['move_gap'] == -1 and check['limits'][0]['station'] == '001'


def test_transient_loss_is_detected_even_with_balanced_closing(snapshot, shift):
    result = deepcopy(snapshot['replay']['plan'])
    row = next(row for row in result['timeline'] if row['kind'] == 'load')
    row['transit'] -= 1
    check = reconcile(shift, result, snapshot['intake'], snapshot['capacity'])
    assert check['fleet_gap'] == 0 and not check['ok']
    assert check['flow_errors'] == [dict(id='M-01', at=row['at'], station='001', station_gap=0, fleet_gap=-1)]


def test_equal_event_count_does_not_mask_duplicate_and_missing_id(snapshot, shift):
    result = deepcopy(snapshot['replay']['plan'])
    row = next(row for row in result['timeline'] if row['id'] == '0001')
    row['id'] = '0002'
    check = reconcile(shift, result, snapshot['intake'], snapshot['capacity'])
    assert check['attempt_gap'] == 2 and not check['ok']
