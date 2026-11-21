import json

from app.config import SAMPLES
from app.errors import DomainError
from .pipeline import run_shift


def sample_sources():
    return {name: (SAMPLES / filename).read_bytes() for name, filename in
            [('events', 'events.csv'), ('capacity', 'capacity.csv'), ('shift', 'shift.json')]}


def sample_plan():
    return json.loads((SAMPLES / 'plan.json').read_bytes())


def seed(store):
    if store.active() is None:
        sources = sample_sources()
        store.publish(run_shift(sources, sample_plan()), sources, None)


def preview(store, run_id, draft):
    store.load(run_id)
    return run_shift(store.sources(run_id), draft)


def publish(store, run_id, *, draft=None, events=None):
    active = store.load(run_id)
    sources = store.sources(run_id)
    if events is not None:
        sources['events'] = events
    snapshot = run_shift(sources, active['dispatch']['legs'] if draft is None else draft)
    created = store.publish(snapshot, sources, run_id)
    new_id = snapshot['manifest']['id']
    return {'id': new_id, 'created': created, 'changed': new_id != run_id}


def restore(store, target, expected):
    snapshot = store.load(target)
    store.publish(snapshot, store.sources(target), expected)
    return {'id': target, 'created': False, 'changed': target != expected}


def rerun(store, expected):
    if store.active() != expected:
        raise DomainError('STALE_RUN', 409, current=store.active())
    return publish(store, expected)
