import re
from collections import defaultdict
from datetime import timedelta

from app.clock import instant, stamp
from app.config import MAX_LEGS
from app.errors import DomainError

FIELDS = {'id', 'truck', 'from', 'to', 'depart', 'arrive', 'count'}


def validate_plan(shift, draft):
    if not isinstance(draft, list) or len(draft) > MAX_LEGS:
        raise DomainError('BAD_PLAN', limit=MAX_LEGS)
    ids, per_truck = set(), defaultdict(list)
    for index, leg in enumerate(draft, 1):
        if not isinstance(leg, dict) or set(leg) != FIELDS:
            raise DomainError('BAD_PLAN', index=index)
        key = leg['id']
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,32}', key) or key in ids:
            raise DomainError('BAD_PLAN', index=index)
        ids.add(key)
        for field in ('truck', 'from', 'to'):
            if not isinstance(leg[field], str):
                raise DomainError('BAD_PLAN', leg=key, field=field)
        if leg['from'] not in shift.stations or leg['to'] not in shift.stations:
            raise DomainError('UNKNOWN_STATION', leg=key)
        if leg['from'] == leg['to']:
            raise DomainError('SAME_STATION', leg=key)
        truck = shift.trucks.get(leg['truck'])
        if truck is None:
            raise DomainError('UNKNOWN_TRUCK', leg=key)
        count = leg['count']
        if type(count) is not int or count < 1:
            raise DomainError('BAD_PLAN', leg=key, field='count')
        if count > truck['load_limit']:
            raise DomainError('TRUCK_LOAD', leg=key, requested=count, available=truck['load_limit'])
        try:
            depart, arrive = instant(leg['depart']), instant(leg['arrive'])
        except DomainError:
            raise DomainError('BAD_TIME', leg=key) from None
        if depart.microsecond % 1000 or arrive.microsecond % 1000:
            raise DomainError('BAD_TIME', leg=key, precision='millisecond')
        if not shift.start <= depart < arrive < shift.end:
            raise DomainError('OUTSIDE_SHIFT', leg=key)
        if arrive - depart < timedelta(minutes=shift.min_travel_minutes):
            raise DomainError('TRAVEL_TIME', leg=key, minutes=shift.min_travel_minutes)
        per_truck[leg['truck']].append(dict(leg, depart=stamp(depart), arrive=stamp(arrive)))
    normalized = []
    for truck_id, legs in per_truck.items():
        truck = shift.trucks[truck_id]
        at, station = instant(truck['available_at']), truck['station']
        for leg in sorted(legs, key=lambda row: (instant(row['depart']), row['id'])):
            if instant(leg['depart']) < at:
                raise DomainError('TRUCK_OVERLAP', leg=leg['id'], available_at=stamp(at))
            if leg['from'] != station:
                raise DomainError('TRUCK_POSITION', leg=leg['id'], station=station)
            at, station = instant(leg['arrive']), leg['to']
            normalized.append(leg)
    return sorted(normalized, key=lambda row: (instant(row['depart']), row['id']))
