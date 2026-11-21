from collections import Counter

from app.config import SLOT_MINUTES
from .buckets import buckets


def demand(shift, result):
    attempts = [row for row in result['timeline'] if row['kind'] in {'rent', 'return'}]
    missed = [row for row in attempts if row['code']]
    return {'missed': missed, 'reasons': dict(Counter(row['code'] for row in missed)),
            'attempted': len(attempts), 'served': len(attempts) - len(missed),
            'slots': buckets(shift, result['timeline']), 'slot_minutes': SLOT_MINUTES}
