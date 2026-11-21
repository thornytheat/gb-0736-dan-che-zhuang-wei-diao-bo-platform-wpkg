import re
from datetime import datetime, timezone

from app.clock import instant, stamp
from app.config import RULE_VERSION, ZONE
from app.errors import DomainError
from app.manifest import canonical, digest
from app.modules.replay.service import replay
from app.shift import load_shift
from .batches import parse_batch
from .merge import merge_events

BATCH_ID = re.compile(r'[A-Za-z0-9_-]{1,32}')


def _values(state, missed):
    return {'available': state['docked'], 'free': state['free'], 'held': state['held'],
            'missed_rent': missed['rent'], 'missed_return': missed['return']}


def _conclusions(result, shift, as_of):
    states = {}
    missed = {code: {'rent': 0, 'return': 0} for code in shift.stations}
    road = shift.opening_road
    for row in result['timeline']:
        if instant(row['at']) > as_of:
            break
        states[row['station']] = row['after']
        road = row['road']
        if row['kind'] in ('rent', 'return') and row['code']:
            missed[row['station']][row['kind']] += 1
    return states, missed, road


def _attempts(timeline, as_of):
    return {row['id']: row for row in timeline
            if row['kind'] in ('rent', 'return') and instant(row['at']) <= as_of}


def _changes(snapshot, result, origin, prior, entries, base_states, base_missed, as_of, previous_id):
    base_attempts = _attempts(snapshot['replay']['plan']['timeline'], as_of)
    merged_attempts = _attempts(result['timeline'], as_of)
    flips = []
    for key, before in base_attempts.items():
        current = merged_attempts.get(key)
        if current is not None and before['code'] != current['code']:
            flips.append({'id': key, 'station': before['station'], 'kind': before['kind'],
                          'at': before['at'], 'before': before['code'], 'after': current['code']})
    introduced = [{'id': key, 'station': row['station'], 'kind': row['kind'], 'at': row['at'],
                   'code': row['code'], 'batch': origin[key]}
                  for key, row in merged_attempts.items() if origin[key] != 'base']
    stations = []
    for entry in entries:
        code = entry['station']
        before = prior.get(code)
        if before is None:
            before_values = {'available': base_states[code]['docked'], 'free': base_states[code]['free'],
                             'missed': base_missed[code]['rent'] + base_missed[code]['return']}
        else:
            before_values = {'available': before['available'], 'free': before['free'],
                             'missed': before['missed_rent'] + before['missed_return']}
        stations.append({'station': code,
                         'before_available': before_values['available'], 'before_free': before_values['free'],
                         'before_missed': before_values['missed'], 'after_available': entry['available'],
                         'after_free': entry['free'], 'after_missed': entry['missed_rent'] + entry['missed_return']})
    order = lambda row: (row['at'], row['id'])
    return {'vs': previous_id or 'base', 'stations': stations,
            'attempts': sorted(flips, key=order), 'introduced': sorted(introduced, key=order)}


def build(snapshot, shift, batches, previous, as_of, mode):
    run_id = snapshot['manifest']['id']
    merged, duplicates, conflicts, origin = merge_events(snapshot['intake']['events'], batches)
    result = replay(shift, merged, snapshot['capacity']['segments'], snapshot['dispatch']['legs'])
    states, missed, road = _conclusions(result, shift, as_of)
    base_states, base_missed, _ = _conclusions(snapshot['replay']['plan'], shift, as_of)
    covered = {}
    for batch in batches:
        at = instant(batch['covered_until'])
        if covered.get(batch['station'], datetime.min.replace(tzinfo=timezone.utc)) < at:
            covered[batch['station']] = at
    previous_id = previous['manifest']['id'] if previous else None
    prior = {row['station']: row for row in previous['stations']} if previous else {}
    entries = []
    for code in shift.stations:
        cov = covered.get(code)
        reported = stamp(cov) if cov is not None else None
        if cov is not None and cov >= as_of:
            entries.append({'station': code, 'status': 'confirmed', 'cutoff': stamp(as_of),
                            'covered_until': reported, 'reported_until': reported, 'reason': None,
                            **_values(states[code], missed[code]),
                            'batches': [batch['id'] for batch in batches if batch['station'] == code],
                            'carried_from': None})
            continue
        reason = 'NO_BACKFILL' if cov is None else 'CUTOFF_SHORT'
        before = prior.get(code)
        if before is None:
            carried = {'cutoff': None, 'covered_until': None, 'batches': [], 'carried_from': None,
                       **_values(base_states[code], base_missed[code])}
        else:
            carried = {'cutoff': before['cutoff'], 'covered_until': before['covered_until'],
                       'batches': before['batches'], 'carried_from': previous_id,
                       **{key: before[key] for key in
                          ('available', 'free', 'held', 'missed_rent', 'missed_return')}}
        entries.append({'station': code, 'status': 'carried', 'reason': reason,
                        'reported_until': reported, **carried})
    changes = _changes(snapshot, result, origin, prior, entries, base_states, base_missed, as_of, previous_id)
    totals = {'available': sum(row['available'] for row in entries),
              'free': sum(row['free'] for row in entries),
              'held': sum(row['held'] for row in entries),
              'missed_rent': sum(row['missed_rent'] for row in entries),
              'missed_return': sum(row['missed_return'] for row in entries),
              'road': road,
              'confirmed': sum(row['status'] == 'confirmed' for row in entries),
              'carried': sum(row['status'] == 'carried' for row in entries),
              'events': len(merged), 'introduced': len(changes['introduced']),
              'duplicates': duplicates, 'conflicts': len(conflicts)}
    public = [{key: row[key] for key in ('station', 'status', 'cutoff', 'reason', 'available',
                                         'free', 'held', 'missed_rent', 'missed_return')}
              for row in entries]
    identity = {'rule_version': RULE_VERSION, 'run': run_id, 'as_of': stamp(as_of),
                'stations': public, 'road': road}
    manifest = {**identity, 'id': digest(canonical(identity).encode()), 'mode': mode,
                'previous': previous_id or 'base',
                'inputs': {'run': run_id, 'batches': {batch['id']: batch['sha256'] for batch in batches}},
                'zone': ZONE, 'generated_at': stamp(datetime.now(timezone.utc))}
    return {'manifest': manifest, 'stations': entries, 'changes': changes, 'totals': totals,
            'conflicts': conflicts}


def _cutoff(value, shift):
    at = instant(value)
    if not shift.start <= at <= shift.end:
        raise DomainError('OUTSIDE_SHIFT')
    return at


def _shift(store, run_id):
    return load_shift(store.sources(run_id)['shift'])


def _previous(store, run_id):
    bulletin_id = store.active_bulletin()
    if bulletin_id is None:
        return None
    previous = store.load_bulletin(bulletin_id)
    return previous if previous['manifest']['run'] == run_id else None


def _default_cutoff(batches, shift):
    covered = [instant(batch['covered_until']) for batch in batches]
    return max(covered) if covered else shift.end


def status(store, as_of=None):
    run_id = store.active()
    snapshot = store.load(run_id)
    shift = _shift(store, run_id)
    batches = store.backfill(run_id)
    as_of = _default_cutoff(batches, shift) if as_of is None else _cutoff(as_of, shift)
    previous = _previous(store, run_id)
    bulletin_id = store.active_bulletin()
    active = store.load_bulletin(bulletin_id) if bulletin_id else None
    view = [{key: batch[key] for key in
             ('id', 'station', 'covered_until', 'received_at', 'sha256', 'accepted', 'quarantined', 'excluded')}
            for batch in batches]
    return {'run': run_id, 'as_of': stamp(as_of), 'active': active,
            'draft': build(snapshot, shift, batches, previous, as_of, 'draft'),
            'batches': view, 'history': store.bulletin_history()}


def ingest(store, batch_id, station, covered_until, raw):
    run_id = store.active()
    shift = _shift(store, run_id)
    if not isinstance(batch_id, str) or not BATCH_ID.fullmatch(batch_id):
        raise DomainError('BAD_BATCH')
    if station not in shift.stations:
        raise DomainError('UNKNOWN_STATION')
    covered = _cutoff(covered_until, shift)
    parsed = parse_batch(raw, shift, station, covered)
    sha256 = digest(canonical({'batch_id': batch_id, 'station': station, 'covered_until': stamp(covered),
                               'events_sha256': digest(raw)}).encode())
    batch = {'id': batch_id, 'station': station, 'covered_until': stamp(covered),
             'received_at': stamp(datetime.now(timezone.utc)), 'sha256': sha256, 'raw': raw,
             'accepted': len(parsed['events']), 'quarantined': len(parsed['excluded'])}
    rows = [{'line': event['line'], 'status': 'accepted', 'code': None,
             'event': canonical(event), 'raw': canonical(event['raw'])} for event in parsed['events']]
    rows += [{'line': row['line'], 'status': 'quarantined', 'code': row['code'],
              'event': None, 'raw': canonical(row['raw'])} for row in parsed['excluded']]
    created = store.add_batch(run_id, batch, rows)
    return {'id': batch_id, 'created': created, 'run': run_id,
            'accepted': batch['accepted'], 'quarantined': batch['quarantined'],
            'reasons': parsed['reasons']}


def publish(store, expected, as_of, mode):
    run_id = store.active()
    snapshot = store.load(run_id)
    shift = _shift(store, run_id)
    batches = store.backfill(run_id)
    previous = _previous(store, run_id)
    payload = build(snapshot, shift, batches, previous, _cutoff(as_of, shift), mode)
    pending = [{'station': row['station'], 'reason': row['reason']}
               for row in payload['stations'] if row['status'] != 'confirmed']
    if pending and (mode == 'all' or len(pending) == len(payload['stations'])):
        raise DomainError('STATIONS_PENDING', 409, stations=pending)
    created = store.publish_bulletin(payload, expected)
    return {'id': payload['manifest']['id'], 'created': created,
            'changed': payload['manifest']['id'] != expected}


def verify(store, bulletin_id):
    stored = store.load_bulletin(bulletin_id)
    manifest = stored['manifest']
    run_id = manifest['run']
    snapshot = store.load(run_id)
    shift = _shift(store, run_id)
    wanted = manifest['inputs']['batches']
    batches = [batch for batch in store.backfill(run_id) if batch['id'] in wanted]
    if {batch['id']: batch['sha256'] for batch in batches} != wanted:
        raise DomainError('BULLETIN_DRIFT', 409, field='batches')
    previous = store.load_bulletin(manifest['previous']) if manifest['previous'] != 'base' else None
    rebuilt = build(snapshot, shift, batches, previous, instant(manifest['as_of']), manifest['mode'])
    rebuilt['manifest']['generated_at'] = manifest['generated_at']
    if rebuilt != stored:
        fields = sorted(key for key in set(rebuilt) | set(stored) if rebuilt.get(key) != stored.get(key))
        raise DomainError('BULLETIN_DRIFT', 409, fields=fields)
    return {'id': bulletin_id, 'ok': True}
