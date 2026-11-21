import re
from collections import defaultdict
from itertools import combinations

from app.clock import instant
from app.errors import DomainError
from app.modules.intake.reader import records

FIELDS = ('station', 'revision', 'start', 'end', 'slots', 'note')


def revisions(raw, shift):
    rows, encoding = records(raw, FIELDS)
    valid, excluded = defaultdict(list), []

    def exclude(row, code):
        excluded.append({'line': row['line'], 'raw': row['raw'], 'code': code})

    for row in rows:
        if row['code']:
            exclude(row, row['code'])
            continue
        fields = row['cells']
        try:
            if fields['station'] not in shift.stations:
                raise DomainError('UNKNOWN_STATION')
            if not all(re.fullmatch(r'[0-9]{1,3}', fields[key]) for key in ('slots', 'revision')):
                raise DomainError('BAD_CAPACITY')
            start, end = instant(fields['start']), instant(fields['end'])
            if end <= start:
                raise DomainError('CAPACITY_INTERVAL')
            if start >= shift.end or end <= shift.start:
                raise DomainError('OUTSIDE_SHIFT')
            rev = int(fields['revision'])
            valid[fields['station'], rev].append(dict(row, start=start, end=end, revision=rev,
                                                       slots=int(fields['slots']), note=fields['note']))
        except DomainError as error:
            exclude(row, error.code)
    survivors = defaultdict(list)
    for (station, _), group in valid.items():
        conflict = set()
        for left, right in combinations(group, 2):
            if left['end'] > right['start'] and left['start'] < right['end']:
                conflict.update((left['line'], right['line']))
        for row in group:
            if row['line'] in conflict:
                exclude(row, 'CAPACITY_CONFLICT')
            else:
                survivors[station].append(row)
    return survivors, sorted(excluded, key=lambda row: row['line']), len(rows), encoding
