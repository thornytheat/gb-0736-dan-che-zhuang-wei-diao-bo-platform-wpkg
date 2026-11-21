from app.clock import instant, stamp
from app.config import LATE_SECONDS
from app.errors import DomainError

FIELDS = ('event_id', 'station', 'kind', 'occurred_at', 'received_at', 'note')
MISSING = {'', '-', 'n/a', 'null', '未知'}


def normalize(cells, shift):
    if any(cells[field].lower() in MISSING for field in FIELDS[:-1]):
        raise DomainError('MISSING_FIELD')
    if cells['station'] not in shift.stations:
        raise DomainError('UNKNOWN_STATION')
    kind = cells['kind'].lower()
    if kind not in {'rent', 'return'}:
        raise DomainError('BAD_KIND')
    occurred, received = instant(cells['occurred_at']), instant(cells['received_at'])
    if not shift.start <= occurred < shift.end:
        raise DomainError('OUTSIDE_SHIFT')
    if received < occurred:
        raise DomainError('RECEIVED_EARLY')
    return {'id': cells['event_id'], 'station': cells['station'], 'kind': kind,
            'at': stamp(occurred), 'received_at': stamp(received),
            'late': (received - occurred).total_seconds() >= LATE_SECONDS, 'note': cells['note']}
