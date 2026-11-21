import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .errors import DomainError
from .manifest import canonical

SCHEMA = '''
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    generated_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sources (
    run_id TEXT NOT NULL REFERENCES runs(id),
    name TEXT NOT NULL,
    raw BLOB NOT NULL,
    PRIMARY KEY (run_id, name)
);
CREATE TABLE IF NOT EXISTS active (
    slot INTEGER PRIMARY KEY CHECK (slot = 1),
    run_id TEXT NOT NULL REFERENCES runs(id)
);
CREATE TABLE IF NOT EXISTS backfill_batches (
    run_id TEXT NOT NULL REFERENCES runs(id),
    id TEXT NOT NULL,
    station TEXT NOT NULL,
    covered_until TEXT NOT NULL,
    received_at TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    raw BLOB NOT NULL,
    accepted INTEGER NOT NULL,
    quarantined INTEGER NOT NULL,
    PRIMARY KEY (run_id, id)
);
CREATE TABLE IF NOT EXISTS backfill_events (
    run_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    line INTEGER NOT NULL,
    status TEXT NOT NULL,
    code TEXT,
    event TEXT,
    raw TEXT NOT NULL,
    PRIMARY KEY (run_id, batch_id, line),
    FOREIGN KEY (run_id, batch_id) REFERENCES backfill_batches(run_id, id)
);
CREATE TABLE IF NOT EXISTS bulletins (
    id TEXT PRIMARY KEY,
    generated_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bulletin_active (
    slot INTEGER PRIMARY KEY CHECK (slot = 1),
    bulletin_id TEXT NOT NULL REFERENCES bulletins(id)
);
'''


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.execute('PRAGMA foreign_keys = ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def active(self):
        with self.connect() as db:
            row = db.execute('SELECT run_id FROM active WHERE slot = 1').fetchone()
        return row[0] if row else None

    def load(self, run_id=None):
        with self.connect() as db:
            if run_id is None:
                row = db.execute('SELECT payload FROM runs JOIN active ON runs.id = active.run_id').fetchone()
            else:
                row = db.execute('SELECT payload FROM runs WHERE id = ?', (run_id,)).fetchone()
        if row is None:
            raise DomainError('RUN_NOT_FOUND', 404)
        return json.loads(row[0])

    def sources(self, run_id):
        with self.connect() as db:
            return dict(db.execute('SELECT name, raw FROM sources WHERE run_id = ?', (run_id,)))

    def history(self):
        sql = '''SELECT runs.id, generated_at, json_extract(payload, '$.shift.name'),
                        json_extract(payload, '$.manifest.inputs.events.sha256'),
                        json_extract(payload, '$.dispatch.comparison.delta'), active.run_id IS NOT NULL
                 FROM runs LEFT JOIN active ON runs.id = active.run_id
                 ORDER BY generated_at DESC, runs.id'''
        keys = ('id', 'generated_at', 'shift', 'source_sha256', 'delta', 'active')
        with self.connect() as db:
            return [dict(zip(keys, row)) for row in db.execute(sql)]

    def publish(self, snapshot, sources, expected):
        manifest = snapshot['manifest']
        run_id = manifest['id']
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT run_id FROM active WHERE slot = 1').fetchone()
            active = row[0] if row else None
            existing = db.execute('SELECT payload FROM runs WHERE id = ?', (run_id,)).fetchone()
            if existing is not None:
                stored = json.loads(existing[0])
                comparable = dict(snapshot, manifest=dict(manifest))
                for key in ('generated_at', 'elapsed_ms'):
                    comparable['manifest'][key] = stored['manifest'][key]
                if stored != comparable:
                    raise DomainError('REPLAY_DRIFT', 409)
                if active == run_id:
                    return False
            if active != expected:
                raise DomainError('STALE_RUN', 409, current=active)
            if existing is None:
                db.execute('INSERT INTO runs VALUES (?, ?, ?)',
                           (run_id, manifest['generated_at'], canonical(snapshot)))
                db.executemany('INSERT INTO sources VALUES (?, ?, ?)',
                               [(run_id, name, raw) for name, raw in sources.items()])
            db.execute('INSERT INTO active VALUES (1, ?) ON CONFLICT(slot) DO UPDATE SET run_id = excluded.run_id',
                       (run_id,))
            return existing is None

    def add_batch(self, run_id, batch, events):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT sha256 FROM backfill_batches WHERE run_id = ? AND id = ?',
                             (run_id, batch['id'])).fetchone()
            if row is not None:
                if row[0] != batch['sha256']:
                    raise DomainError('BATCH_CONFLICT', 409, batch=batch['id'])
                return False
            db.execute('INSERT INTO backfill_batches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                       (run_id, batch['id'], batch['station'], batch['covered_until'], batch['received_at'],
                        batch['sha256'], batch['raw'], batch['accepted'], batch['quarantined']))
            db.executemany('INSERT INTO backfill_events VALUES (?, ?, ?, ?, ?, ?, ?)',
                           [(run_id, batch['id'], row['line'], row['status'], row['code'], row['event'], row['raw'])
                            for row in events])
            return True

    def batches(self, run_id):
        keys = ('id', 'station', 'covered_until', 'received_at', 'sha256', 'accepted', 'quarantined')
        with self.connect() as db:
            rows = db.execute('''SELECT id, station, covered_until, received_at, sha256, accepted, quarantined
                                 FROM backfill_batches WHERE run_id = ? ORDER BY received_at, id''', (run_id,))
            return [dict(zip(keys, row)) for row in rows]

    def backfill(self, run_id):
        batches = self.batches(run_id)
        for batch in batches:
            batch.update(events=[], excluded=[])
        index = {batch['id']: batch for batch in batches}
        sql = 'SELECT batch_id, status, code, event, raw FROM backfill_events WHERE run_id = ? ORDER BY line'
        with self.connect() as db:
            for batch_id, status, code, event, raw in db.execute(sql, (run_id,)):
                batch = index[batch_id]
                if status == 'accepted':
                    batch['events'].append(json.loads(event))
                else:
                    batch['excluded'].append({'code': code, 'raw': json.loads(raw)})
        return batches

    def active_bulletin(self):
        with self.connect() as db:
            row = db.execute('SELECT bulletin_id FROM bulletin_active WHERE slot = 1').fetchone()
        return row[0] if row else None

    def load_bulletin(self, bulletin_id=None):
        with self.connect() as db:
            if bulletin_id is None:
                row = db.execute('''SELECT payload FROM bulletins
                                    JOIN bulletin_active ON bulletins.id = bulletin_active.bulletin_id''').fetchone()
            else:
                row = db.execute('SELECT payload FROM bulletins WHERE id = ?', (bulletin_id,)).fetchone()
        if row is None:
            raise DomainError('BULLETIN_NOT_FOUND', 404)
        return json.loads(row[0])

    def bulletin_history(self):
        sql = '''SELECT bulletins.id, generated_at, json_extract(payload, '$.manifest.mode'),
                        json_extract(payload, '$.manifest.as_of'), bulletin_active.bulletin_id IS NOT NULL
                 FROM bulletins LEFT JOIN bulletin_active ON bulletins.id = bulletin_active.bulletin_id
                 ORDER BY generated_at DESC, bulletins.id'''
        keys = ('id', 'generated_at', 'mode', 'as_of', 'active')
        with self.connect() as db:
            return [dict(zip(keys, row)) for row in db.execute(sql)]

    def publish_bulletin(self, snapshot, expected):
        bulletin_id = snapshot['manifest']['id']
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT bulletin_id FROM bulletin_active WHERE slot = 1').fetchone()
            active = row[0] if row else None
            existing = db.execute('SELECT 1 FROM bulletins WHERE id = ?', (bulletin_id,)).fetchone()
            if existing is not None and active == bulletin_id:
                return False
            if active != expected:
                raise DomainError('STALE_BULLETIN', 409, current=active)
            if existing is None:
                db.execute('INSERT INTO bulletins VALUES (?, ?, ?)',
                           (bulletin_id, snapshot['manifest']['generated_at'], canonical(snapshot)))
            db.execute('''INSERT INTO bulletin_active VALUES (1, ?)
                          ON CONFLICT(slot) DO UPDATE SET bulletin_id = excluded.bulletin_id''', (bulletin_id,))
            return existing is None
