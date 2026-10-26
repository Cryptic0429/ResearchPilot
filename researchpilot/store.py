import json
from contextlib import contextmanager
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
import uuid


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / "researchpilot.sqlite3"
        self.lock = threading.RLock()
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY, kind TEXT NOT NULL,
                    title TEXT NOT NULL, body TEXT NOT NULL, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL, detail TEXT NOT NULL, created TEXT NOT NULL);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(str(self.path), timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, key, default=None):
        with self.connection() as db:
            row = db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        with self.lock, self.connection() as db:
            db.execute("INSERT OR REPLACE INTO kv VALUES (?,?)", (key, json.dumps(value, ensure_ascii=False)))

    def add(self, kind, title, body):
        item = dict(id=uuid.uuid4().hex, kind=kind, title=title[:200], body=body, created=now())
        with self.connection() as db:
            db.execute("INSERT INTO items VALUES (?,?,?,?,?)", (item['id'], kind, item['title'], json.dumps(body, ensure_ascii=False), item['created']))
        return item

    def items(self):
        with self.connection() as db:
            rows = db.execute("SELECT * FROM items ORDER BY created DESC, rowid DESC LIMIT 300").fetchall()
        return [{**dict(r), 'body': json.loads(r['body'])} for r in rows]

    def delete(self, item_id):
        with self.connection() as db:
            db.execute("DELETE FROM items WHERE id=?", (item_id,))

    def event(self, action, detail):
        with self.connection() as db:
            db.execute("INSERT INTO events(action,detail,created) VALUES (?,?,?)", (action, json.dumps(detail, ensure_ascii=False), now()))

    def events(self):
        with self.connection() as db:
            return [dict(r) for r in db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 100")]
