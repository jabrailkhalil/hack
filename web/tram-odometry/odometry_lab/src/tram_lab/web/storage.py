from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import sqlite3
import uuid


@dataclass
class Settings:
    dataset: Path
    cache: Path
    runs: Path
    models: Path
    state: Path

    @classmethod
    def environment(cls):
        return cls(*(Path(os.environ.get('TRAM_' + k.upper(), default)).resolve() for k, default in
                     [('dataset', '../dataset'), ('cache', '.cache/web'), ('runs', 'runs'),
                      ('models', 'models'), ('state', '.web-state')]))

    def prepare(self):
        for path in (self.cache, self.runs, self.models, self.state):
            path.mkdir(parents=True, exist_ok=True)


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, settings):
        settings.prepare()
        self.path = settings.state / 'jobs.sqlite3'
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, kind TEXT, status TEXT, created TEXT, updated TEXT, request TEXT, result TEXT, error TEXT, log TEXT)')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def decode(row):
        if row is None:
            raise KeyError('Задание не найдено')
        item = dict(row)
        for field in ('request', 'result'):
            item[field] = json.loads(item[field]) if item[field] else None
        return item

    def create(self, kind, request):
        identity = uuid.uuid4().hex
        stamp = now()
        with self.connect() as db:
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)',
                       (identity, kind, 'queued', stamp, stamp, json.dumps(request, allow_nan=False), None, None, ''))
        return self.get(identity)

    def get(self, identity):
        with self.connect() as db:
            return self.decode(db.execute('SELECT * FROM jobs WHERE id=?', (identity,)).fetchone())

    def list(self):
        with self.connect() as db:
            return [self.decode(row) for row in db.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 200')]

    def update(self, identity, **fields):
        if not set(fields) <= {'status', 'result', 'error'}:
            raise ValueError('Invalid job fields')
        if 'result' in fields:
            fields['result'] = json.dumps(fields['result'], allow_nan=False)
        fields['updated'] = now()
        with self.connect() as db:
            db.execute('UPDATE jobs SET ' + ','.join(f'{k}=?' for k in fields) + ' WHERE id=?', (*fields.values(), identity))

    def log(self, identity, message):
        with self.connect() as db:
            db.execute("UPDATE jobs SET log=substr(log || ?, -60000), updated=? WHERE id=?", (now() + ' ' + str(message) + '\n', now(), identity))

    def claim(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if row:
                db.execute("UPDATE jobs SET status='running',updated=? WHERE id=?", (now(), row['id']))
                return self.decode(row)

    def cancel(self, identity):
        with self.connect() as db:
            db.execute("UPDATE jobs SET status=CASE WHEN status='queued' THEN 'cancelled' ELSE 'cancelling' END, updated=? WHERE id=? AND status IN ('queued','running')", (now(), identity))
        return self.get(identity)

    def recover(self):
        with self.connect() as db:
            db.execute("UPDATE jobs SET status='interrupted',error='Worker перезапущен; повторите задание',updated=? WHERE status IN ('running','cancelling')", (now(),))


def safe_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Недопустимый путь')
    return path
