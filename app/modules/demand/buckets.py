from datetime import timedelta

from app.clock import instant, stamp
from app.config import SLOT_MINUTES


def buckets(shift, timeline):
    step = timedelta(minutes=SLOT_MINUTES)
    size = -(-(shift.end - shift.start) // step)
    cells = {station: [{'at': stamp(shift.start + index * step), 'rents': 0, 'returns': 0,
                        'missed_rent': 0, 'missed_return': 0} for index in range(size)]
             for station in shift.stations}
    grouped = {station: [[] for _ in range(size)] for station in shift.stations}
    for row in timeline:
        index = (instant(row['at']) - shift.start) // step
        grouped[row['station']][index].append(row)
    result = []
    for station, slots in cells.items():
        state = None
        for cell, rows in zip(slots, grouped[station]):
            for row in rows:
                state = row['after']
                if row['kind'] == 'rent':
                    cell['rents'] += 1
                    cell['missed_rent'] += bool(row['code'])
                elif row['kind'] == 'return':
                    cell['returns'] += 1
                    cell['missed_return'] += bool(row['code'])
            result.append(dict(cell, station=station, **state))
    return result
