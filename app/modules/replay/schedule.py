from app.clock import instant


def ordered(events, segments, legs):
    steps = [(instant(row['start']), 0, row['station'], row) for row in segments]
    for leg in legs:
        steps.append((instant(leg['arrive']), 1, leg['id'], leg))
        steps.append((instant(leg['depart']), 2, leg['id'], leg))
    steps.extend((instant(event['at']), 3, event['id'], event) for event in events)
    return sorted(steps, key=lambda row: row[:3])
