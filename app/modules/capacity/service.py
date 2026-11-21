from app.clock import stamp
from app.errors import DomainError
from .versions import revisions


def capacity(raw, shift):
    versions, excluded, count, encoding = revisions(raw, shift)
    segments = []
    for station in shift.stations:
        candidates = versions[station]
        edges = {shift.start, shift.end}
        for row in candidates:
            edges.update((max(row['start'], shift.start), min(row['end'], shift.end)))
        edges = sorted(edges)
        for start, end in zip(edges, edges[1:]):
            active = [row for row in candidates if row['start'] <= start < row['end']]
            if not active:
                raise DomainError('CAPACITY_GAP', station=station, at=stamp(start))
            chosen = max(active, key=lambda row: row['revision'])
            if segments and segments[-1]['line'] == chosen['line']:
                segments[-1]['end'] = stamp(end)
                continue
            segments.append({'station': station, 'start': stamp(start), 'end': stamp(end),
                             **{key: chosen[key] for key in ('revision', 'slots', 'line', 'note', 'raw')}})
    return {'segments': segments, 'input_rows': count, 'excluded': excluded,
            'accepted': sum(map(len, versions.values())), 'encoding': encoding}
