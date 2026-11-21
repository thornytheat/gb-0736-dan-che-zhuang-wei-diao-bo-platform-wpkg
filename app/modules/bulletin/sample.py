import json

from app.config import SAMPLES
from .service import ingest

BACKFILL = SAMPLES / 'backfill'


def sample_batches():
    return json.loads((BACKFILL / 'batches.json').read_bytes())


def remaining(store):
    run_id = store.active()
    existing = {batch['id'] for batch in store.batches(run_id)}
    return [item for item in sample_batches() if item['batch_id'] not in existing]


def ingest_next_sample(store):
    pending = remaining(store)
    if not pending:
        return {'id': None, 'created': False, 'remaining': 0}
    item = pending[0]
    raw = (BACKFILL / item['file']).read_bytes()
    result = ingest(store, item['batch_id'], item['station'], item['covered_until'], raw)
    return {**result, 'remaining': len(pending) - 1}
