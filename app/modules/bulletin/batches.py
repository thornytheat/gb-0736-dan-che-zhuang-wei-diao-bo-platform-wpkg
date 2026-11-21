from collections import Counter

from app.clock import instant
from app.errors import DomainError
from app.modules.intake.normalize import FIELDS
from app.modules.intake.reader import records
from app.modules.intake.service import select


def parse_batch(raw, shift, station, covered_until):
    try:
        rows, encoding = records(raw, FIELDS)
    except DomainError as error:
        if error.code != 'HEADER_ONLY':
            raise
        return {'encoding': None, 'input_rows': 0, 'events': [], 'excluded': [], 'reasons': {}}

    def local(event):
        if event['station'] != station:
            raise DomainError('FOREIGN_STATION')
        if instant(event['at']) > covered_until:
            raise DomainError('BEYOND_COVERAGE')

    accepted, excluded = select(rows, shift, checks=(local,))
    return {'encoding': encoding, 'input_rows': len(rows), 'events': accepted,
            'excluded': excluded, 'reasons': dict(Counter(row['code'] for row in excluded))}
