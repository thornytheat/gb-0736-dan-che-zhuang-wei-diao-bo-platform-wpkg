from collections import Counter


def compare(shift, before, after):
    def attempts(result):
        return {row['id']: row for row in result['timeline'] if row['kind'] in {'rent', 'return'}}

    base, candidate = attempts(before), attempts(after)
    changes = []
    counters = Counter()
    for key, previous in base.items():
        current = candidate[key]
        counters[previous['station'], 'before'] += bool(previous['code'])
        counters[previous['station'], 'after'] += bool(current['code'])
        if previous['code'] != current['code']:
            changes.append({'id': key, 'line': previous['line'], 'station': previous['station'],
                            'kind': previous['kind'], 'at': previous['at'],
                            'before': previous['code'], 'after': current['code']})
    stations = []
    for station in shift.stations:
        first, last = counters[station, 'before'], counters[station, 'after']
        stations.append({'station': station, 'before': first, 'after': last, 'delta': last - first})
    first, last = (sum(row[key] for row in stations) for key in ('before', 'after'))
    return {'before': first, 'after': last, 'delta': last - first, 'stations': stations, 'changes': changes,
            'recovered': sum(row['after'] is None for row in changes),
            'newly_missed': sum(row['before'] is None for row in changes)}
