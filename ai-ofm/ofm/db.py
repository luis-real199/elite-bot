import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts(
  id INTEGER PRIMARY KEY,
  batch TEXT NOT NULL,
  slot_at TEXT NOT NULL,
  kind TEXT NOT NULL,
  targets TEXT NOT NULL,
  idea TEXT, image_prompt TEXT, motion_prompt TEXT, caption TEXT, hashtags TEXT,
  status TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  image_url TEXT, video_url TEXT, media_path TEXT, public_url TEXT,
  review_message_id INTEGER,
  sent_to_fanvue INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS posts_status ON posts(status);
CREATE TABLE IF NOT EXISTS publications(
  id INTEGER PRIMARY KEY,
  post_id INTEGER NOT NULL REFERENCES posts(id),
  target TEXT NOT NULL,
  status TEXT NOT NULL,
  due_at TEXT,
  external_id TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  updated_at TEXT NOT NULL,
  UNIQUE(post_id, target)
);
CREATE TABLE IF NOT EXISTS costs(
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  kind TEXT NOT NULL,
  usd REAL NOT NULL,
  detail TEXT
);
CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def utcnow():
    return datetime.now(timezone.utc)


class Post(dict):
    """A posts row with decoded JSON columns; keys are also attributes."""

    __getattr__ = dict.get

    @property
    def social_targets(self):
        return [t for t in self["targets"] if t != "fanvue"]


class DB:
    def __init__(self, path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def _post(self, row):
        if row is None:
            return None
        post = Post(dict(row))
        post["targets"] = json.loads(post["targets"])
        post["hashtags"] = json.loads(post["hashtags"] or "[]")
        post["slot_at"] = datetime.fromisoformat(post["slot_at"])
        return post

    def insert_post(self, **fields):
        now = utcnow().isoformat()
        fields = {**fields, "created_at": now, "updated_at": now}
        fields["targets"] = json.dumps(fields["targets"])
        fields["hashtags"] = json.dumps(fields.get("hashtags") or [], ensure_ascii=False)
        fields["slot_at"] = fields["slot_at"].isoformat()
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        with self.conn:
            cur = self.conn.execute(f"INSERT INTO posts({cols}) VALUES ({marks})", list(fields.values()))
        return cur.lastrowid

    def update_post(self, post_id, **fields):
        fields["updated_at"] = utcnow().isoformat()
        sets = ", ".join(f"{k} = ?" for k in fields)
        with self.conn:
            self.conn.execute(f"UPDATE posts SET {sets} WHERE id = ?", [*fields.values(), post_id])

    def get_post(self, post_id):
        return self._post(self.conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone())

    def posts(self, status=None, limit=None):
        sql = "SELECT * FROM posts"
        args = []
        if status:
            statuses = [status] if isinstance(status, str) else list(status)
            sql += f" WHERE status IN ({', '.join('?' for _ in statuses)})"
            args += statuses
        sql += " ORDER BY slot_at, id"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [self._post(r) for r in self.conn.execute(sql, args)]

    def recent_ideas(self, limit=40):
        rows = self.conn.execute("SELECT idea FROM posts WHERE idea IS NOT NULL ORDER BY id DESC LIMIT ?", (limit,))
        return [r["idea"] for r in rows]

    def status_counts(self, since=None):
        sql = "SELECT status, COUNT(*) n FROM posts"
        args = []
        if since:
            sql += " WHERE created_at >= ?"
            args.append(since.isoformat())
        sql += " GROUP BY status"
        return {r["status"]: r["n"] for r in self.conn.execute(sql, args)}

    def publication(self, post_id, target):
        row = self.conn.execute(
            "SELECT * FROM publications WHERE post_id = ? AND target = ?", (post_id, target)
        ).fetchone()
        return dict(row) if row else None

    def save_publication(self, post_id, target, status, due_at=None, external_id=None, error=None):
        prev = self.publication(post_id, target)
        attempts = (prev["attempts"] if prev else 0) + (1 if status == "failed" else 0)
        with self.conn:
            self.conn.execute(
                """INSERT INTO publications(post_id, target, status, due_at, external_id, attempts, error, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(post_id, target) DO UPDATE SET status = excluded.status,
                     due_at = excluded.due_at, external_id = excluded.external_id,
                     attempts = excluded.attempts, error = excluded.error, updated_at = excluded.updated_at""",
                (post_id, target, status, due_at, external_id, attempts, error, utcnow().isoformat()),
            )

    def publication_counts(self, since):
        rows = self.conn.execute(
            "SELECT status, COUNT(*) n FROM publications WHERE updated_at >= ? GROUP BY status", (since.isoformat(),)
        )
        return {r["status"]: r["n"] for r in rows}

    def add_cost(self, kind, usd, detail=""):
        with self.conn:
            self.conn.execute(
                "INSERT INTO costs(ts, kind, usd, detail) VALUES (?, ?, ?, ?)",
                (utcnow().isoformat(), kind, float(usd), detail),
            )

    def spent(self, since, include_setup=False):
        sql = "SELECT COALESCE(SUM(usd), 0) s FROM costs WHERE ts >= ?"
        if not include_setup:
            sql += " AND kind NOT LIKE 'setup%'"
        return self.conn.execute(sql, (since.isoformat(),)).fetchone()["s"]

    def spent_last_week(self):
        return self.spent(utcnow() - timedelta(days=7))

    def kv_get(self, key, default=None):
        row = self.conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def kv_set(self, key, value):
        with self.conn:
            self.conn.execute(
                "INSERT INTO kv(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value, ensure_ascii=False)),
            )
