from app.clock import stamp
from app.errors import DomainError
from .schedule import ordered
from .state import Dock, attempt


def replay(shift, events, segments, legs=()):
    docks = {code: Dock(0, row['opening']) for code, row in shift.stations.items()}
    road, transit = shift.opening_road, 0
    timeline = []
    for at, priority, key, row in ordered(events, segments, legs):
        station = row[['station', 'to', 'from', 'station'][priority]]
        dock = docks[station]
        previous = dock.public()
        code = None
        line = row.get('line')
        if priority == 0:
            kind = 'capacity'
            dock.capacity, dock.version_line = row['slots'], line
            dock.reseat()
        elif priority == 1:
            kind = 'unload'
            if dock.free < row['count']:
                raise DomainError('DROP_FULL', leg=key, station=station, at=stamp(at),
                                  available=dock.free, requested=row['count'], version_line=dock.version_line)
            dock.docked += row['count']
            transit -= row['count']
        elif priority == 2:
            kind = 'load'
            if dock.docked < row['count']:
                raise DomainError('PICKUP_SHORT', leg=key, station=station, at=stamp(at),
                                  available=dock.docked, requested=row['count'], version_line=dock.version_line)
            dock.docked -= row['count']
            transit += row['count']
            dock.reseat()
        else:
            kind = row['kind']
            code, road = attempt(dock, kind, road)
        timeline.append({'at': stamp(at), 'id': key, 'kind': kind, 'station': station, 'line': line,
                         'code': code, 'late': row.get('late', False), 'before': previous,
                         'after': dock.public(), 'road': road, 'transit': transit,
                         'quantity': row.get('count', 0 if code or kind == 'capacity' else 1)})
    return {'timeline': timeline, 'closing': {code: dock.public() for code, dock in docks.items()},
            'road': road, 'transit': transit}
