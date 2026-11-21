from collections import Counter

from .stations import SIGNS, station_ledgers


def check_timeline(shift, timeline):
    limits, flow_errors = [], []
    totals = {code: station['opening'] for code, station in shift.stations.items()}
    fleet = sum(totals.values()) + shift.opening_road
    for row in timeline:
        state = row['after']
        evidence = {'id': row['id'], 'at': row['at'], 'station': row['station']}
        if (not 0 <= state['docked'] <= state['capacity'] or state['held'] < 0
                or row['road'] < 0 or row['transit'] < 0):
            limits.append(evidence)
        station = row['station']
        expected = totals[station] + SIGNS.get(row['kind'], 0) * row['quantity']
        totals[station] = state['docked'] + state['held']
        fleet_gap = sum(totals.values()) + row['road'] + row['transit'] - fleet
        if totals[station] != expected or fleet_gap:
            flow_errors.append(dict(evidence, station_gap=totals[station] - expected, fleet_gap=fleet_gap))
    return limits, flow_errors


def reconcile(shift, result, intake, capacity):
    stations = station_ledgers(shift, result)
    opening = sum(row['opening'] for row in stations) + shift.opening_road
    closing = sum(row['closing'] for row in stations) + result['road'] + result['transit']
    road_expected = shift.opening_road + sum(row['rent'] - row['return'] for row in stations)
    move_gap = sum(row['load'] - row['unload'] for row in stations) - result['transit']
    input_gap = intake['input_rows'] - len(intake['events']) - len(intake['excluded'])
    capacity_gap = capacity['input_rows'] - capacity['accepted'] - len(capacity['excluded'])
    road_gap = result['road'] - road_expected
    timeline = result['timeline']
    observed = Counter(row['id'] for row in timeline if row['kind'] in {'rent', 'return'})
    expected = Counter(row['id'] for row in intake['events'])
    attempt_gap = sum((expected - observed).values()) + sum((observed - expected).values())
    limits, flow_errors = check_timeline(shift, timeline)
    ok = not (closing - opening or move_gap or input_gap or capacity_gap or road_gap or attempt_gap
              or result['transit'] or limits or flow_errors or any(row['gap'] for row in stations))
    return {'ok': ok, 'stations': stations, 'start_fleet': opening, 'end_fleet': closing,
            'fleet_gap': closing - opening, 'road_opening': shift.opening_road, 'road_end': result['road'],
            'road_gap': road_gap, 'in_transit_end': result['transit'], 'move_gap': move_gap,
            'intake_gap': input_gap, 'capacity_gap': capacity_gap, 'attempt_gap': attempt_gap, 'limits': limits,
            'flow_errors': flow_errors}
