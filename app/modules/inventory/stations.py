from collections import Counter

SIGNS = {'rent': -1, 'return': 1, 'load': -1, 'unload': 1}


def station_ledgers(shift, result):
    flows = Counter()
    for row in result['timeline']:
        if row['kind'] in SIGNS and not row['code']:
            flows[row['station'], row['kind']] += row['quantity']
    stations = []
    for code, config in shift.stations.items():
        start, closing = config['opening'], result['closing'][code]
        counts = {kind: flows[code, kind] for kind in SIGNS}
        expected = start + sum(counts[kind] * sign for kind, sign in SIGNS.items())
        end = closing['docked'] + closing['held']
        stations.append(dict(counts, station=code, opening=start, docked=closing['docked'],
                             held=closing['held'], expected=expected, closing=end, gap=end - expected))
    return stations
