
def get_slot(snapshot, station='002', minute='00', mode='plan'):
    return next(row for row in snapshot['demand'][mode]['slots']
                if row['station'] == station and row['at'] == f'2026-11-20T00:{minute}:00Z')


def test_preserves_demand_even_when_business_does_not_transact(snapshot):
    base = snapshot['demand']['base']
    assert (base['attempted'], base['served'], len(base['missed'])) == (50, 39, 11)
    assert base['reasons'] == {'NO_DOCK': 4, 'NO_BIKE': 5, 'STATION_CLOSED': 2}


def test_empty_and_full_conditions_are_distinct(snapshot):
    base = {row['id']: row for row in snapshot['demand']['base']['missed']}
    assert (base['0005']['kind'], base['0005']['code']) == ('return', 'NO_DOCK')
    assert (base['0006']['kind'], base['0006']['code']) == ('rent', 'NO_BIKE')


# TRAP-23
def test_boundary_bucketing_does_not_double_count(snapshot):
    first = get_slot(snapshot)
    second = get_slot(snapshot, minute='15')
    assert (first['rents'], first['missed_rent'], first['docked']) == (4, 1, 2)
    assert (second['rents'], second['missed_rent'], second['returns']) == (3, 0, 1)


def test_incident_slot_carries_holding_state(snapshot):
    slot = get_slot(snapshot, station='003', minute='30')
    assert (slot['capacity'], slot['docked'], slot['held'], slot['missed_rent'], slot['missed_return']) == (0, 0, 7, 1, 1)


def test_empty_slots_are_present_with_previous_state(snapshot):
    slot = get_slot(snapshot, station='003', minute='15')
    assert (slot['rents'], slot['returns'], slot['docked'], slot['free']) == (0, 0, 7, 1)
    assert len(snapshot['demand']['base']['slots']) == 32


def test_all_slot_attempts_match_source_total(snapshot):
    for result in snapshot['demand'].values():
        assert sum(row['rents'] + row['returns'] for row in result['slots']) == 50
        assert sum(row['missed_rent'] + row['missed_return'] for row in result['slots']) == len(result['missed'])
