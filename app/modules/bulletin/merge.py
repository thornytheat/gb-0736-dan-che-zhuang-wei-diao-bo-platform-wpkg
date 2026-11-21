from app.clock import instant


def merge_events(base_events, batches):
    groups = {}
    for event in base_events:
        groups.setdefault(event['id'], []).append(('base', None, event))
    for batch in batches:
        for event in batch['events']:
            groups.setdefault(event['id'], []).append(('batch', batch['id'], event))
    merged, conflicts, origin = [], [], {}
    duplicates = 0
    for event_id, pairs in groups.items():
        identities = {(event['station'], event['kind'], event['at']) for _, _, event in pairs}
        if len(identities) > 1:
            sources = sorted({'base' if source == 'base' else batch_id for source, batch_id, _ in pairs})
            conflicts.append({'id': event_id, 'sources': sources, 'rows': len(pairs)})
            continue
        duplicates += len(pairs) - 1

        def rank(pair):
            source, batch_id, event = pair
            return (instant(event['received_at']), 0 if source == 'base' else 1,
                    batch_id or '', event['line'])

        source, batch_id, event = min(pairs, key=rank)
        origin[event_id] = batch_id or 'base'
        merged.append(event)
    merged.sort(key=lambda event: (instant(event['at']), event['id']))
    return merged, duplicates, conflicts, origin
