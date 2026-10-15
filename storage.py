"""Local sources, immutable analysis snapshots, and Slack event state."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from urllib.parse import urlparse


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS analyses (id INTEGER PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, status TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS threads (id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS replies (id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS learning_threads (id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS learning_drafts (id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS learning_posts (
                    thread_id TEXT NOT NULL, ts TEXT NOT NULL, body TEXT NOT NULL,
                    PRIMARY KEY(thread_id, ts));
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    def import_sources(self, records):
        if not isinstance(records, list):
            raise ValueError("자료는 JSON 배열이어야 합니다")
        for s in records:
            required = ("id", "kind", "ticker", "title", "text", "url", "published_at",
                        "observed_at", "valid_until", "reviewed", "synthetic")
            if not isinstance(s, dict) or any(k not in s for k in required):
                raise ValueError("자료 필드가 부족합니다")
            if any(not isinstance(s[k], str) or not s[k].strip() for k in required[:-2]):
                raise ValueError("자료 문자열은 비어 있을 수 없습니다")
            if s["kind"] not in {"principle", "financial", "market", "sector", "document", "perspective_material"}:
                raise ValueError("알 수 없는 자료 종류")
            if not all(type(s[k]) is bool for k in ("reviewed", "synthetic")):
                raise ValueError("reviewed/synthetic은 boolean이어야 합니다")
            parsed = urlparse(s["url"])
            remote = parsed.scheme in {"http", "https"} and bool(parsed.netloc)
            local = parsed.scheme == "file" and parsed.netloc == "" and parsed.path.startswith("/")
            if not (remote or local):
                raise ValueError("자료에 http(s) 출처가 필요합니다")
            for k in ("published_at", "observed_at", "valid_until"):
                date.fromisoformat(s[k])
            if s["observed_at"] > s["valid_until"]:
                raise ValueError("유효기간이 관측일보다 빠릅니다")
        with self.connect() as db:
            db.executemany("INSERT OR REPLACE INTO sources VALUES (?, ?)",
                           [(s["id"], json.dumps(s, ensure_ascii=False)) for s in records])

    def sources(self, as_of):
        date.fromisoformat(as_of)
        with self.connect() as db:
            records = [json.loads(row[0]) for row in db.execute("SELECT body FROM sources ORDER BY id")]
        return [s for s in records if s["published_at"] <= as_of and s["observed_at"] <= as_of
                and s["valid_until"] >= as_of]

    def save_analysis(self, record):
        with self.connect() as db:
            cursor = db.execute("INSERT INTO analyses(body) VALUES (?)", (json.dumps(record, ensure_ascii=False),))
            return cursor.lastrowid

    def history(self):
        with self.connect() as db:
            return [dict(json.loads(body), analysis_id=id) for id, body in
                    db.execute("SELECT id, body FROM analyses ORDER BY id DESC")]

    def claim_event(self, event_id):
        with self.connect() as db:
            try:
                db.execute("INSERT INTO events VALUES (?, 'processing')", (event_id,))
                return True
            except sqlite3.IntegrityError:
                return False

    def finish_event(self, event_id):
        with self.connect() as db:
            db.execute("UPDATE events SET status='done' WHERE id=?", (event_id,))

    def release_event(self, event_id):
        with self.connect() as db:
            db.execute("DELETE FROM events WHERE id=? AND status='processing'", (event_id,))

    def get(self, table, key):
        if table not in {"threads", "replies", "learning_threads", "learning_drafts"}:
            raise ValueError("Unknown table")
        with self.connect() as db:
            row = db.execute("SELECT body FROM " + table + " WHERE id=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, table, key, record):
        if table not in {"threads", "replies", "learning_threads", "learning_drafts"}:
            raise ValueError("Unknown table")
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO " + table + " VALUES (?, ?)",
                       (key, json.dumps(record, ensure_ascii=False)))

    def save_learning_post(self, thread_id, event):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO learning_posts VALUES (?, ?, ?)",
                       (thread_id, event["ts"], json.dumps(event, ensure_ascii=False)))

    def learning_posts(self, thread_id):
        with self.connect() as db:
            rows = db.execute("SELECT body FROM learning_posts WHERE thread_id=? ORDER BY ts", (thread_id,))
            return [json.loads(row[0]) for row in rows]

    def approve_learning(self, key, state, sources):
        """Replace only this thread's active sources in one transaction."""
        with self.connect() as db:
            for id, body in db.execute("SELECT id, body FROM sources").fetchall():
                if json.loads(body).get("learning_thread") == key:
                    db.execute("DELETE FROM sources WHERE id=?", (id,))
            db.executemany("INSERT OR REPLACE INTO sources VALUES (?, ?)",
                           [(s["id"], json.dumps(s, ensure_ascii=False)) for s in sources])
            db.execute("INSERT OR REPLACE INTO learning_threads VALUES (?, ?)",
                       (key, json.dumps(state, ensure_ascii=False)))
