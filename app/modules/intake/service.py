from collections import Counter, defaultdict

from app.clock import instant
from app.errors import DomainError
from .normalize import FIELDS, normalize
from .reader import records


def intake(raw, shift):
    rows, encoding = records(raw, FIELDS)
    groups = defaultdict(list)
    accepted, excluded = [], []

    def exclude(row, code):
        excluded.append({'line': row['line'], 'raw': row['raw'], 'code': code})

    for row in rows:
        if row['code']:
            exclude(row, row['code'])
            continue
        try:
            event = normalize(row['cells'], shift)
        except DomainError as error:
            exclude(row, error.code)
            continue
        groups[event['id']].append((row, event))
    for group in groups.values():
        identities = {(event['station'], event['kind'], event['at']) for _, event in group}
        if len(identities) > 1:
            for row, _ in group:
                exclude(row, 'EVENT_CONFLICT')
            continue
        group.sort(key=lambda pair: (instant(pair[1]['received_at']), pair[0]['line']))
        row, event = group[0]
        accepted.append(dict(event, line=row['line'], raw=row['raw']))
        for row, _ in group[1:]:
            exclude(row, 'DUPLICATE_EVENT')
    accepted.sort(key=lambda event: (instant(event['at']), event['id']))
    return {'encoding': encoding, 'input_rows': len(rows), 'events': accepted,
            'excluded': sorted(excluded, key=lambda row: row['line']),
            'reasons': dict(Counter(row['code'] for row in excluded)),
            'late': sum(event['late'] for event in accepted)}
