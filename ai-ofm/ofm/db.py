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
CREATE TABLE IF NOT EXISTS fanvue_media(
  id INTEGER PRIMARY KEY,
  post_id INTEGER NOT NULL REFERENCES posts(id),
  media_uuid TEXT NOT NULL,
  purpose TEXT NOT NULL,
  batch TEXT,
  description TEXT,
  fanvue_post_uuid TEXT,
  publish_at TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_seen(fan_uuid TEXT PRIMARY KEY, message_uuid TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS chat_drafts(
  id INTEGER PRIMARY KEY,
  fan_uuid TEXT NOT NULL,
  fan_name TEXT,
  text TEXT NOT NULL,
  offer_media_uuid TEXT,
  offer_price_cents INTEGER,
  reason TEXT,
  status TEXT NOT NULL,
  tg_message_id INTEGER,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS offers(
  fan_uuid TEXT NOT NULL,
  media_uuid TEXT NOT NULL,
  price_cents INTEGER,
  ts TEXT NOT NULL,
  PRIMARY KEY(fan_uuid, media_uuid)
);
CREATE TABLE IF NOT EXISTS swipes(
  id INTEGER PRIMARY KEY,
  text TEXT NOT NULL,
  ts TEXT NOT NULL,
  used INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS fan_requests(
  id INTEGER PRIMARY KEY,
  fan_uuid TEXT,
  text TEXT NOT NULL,
  ts TEXT NOT NULL,
  used INTEGER NOT NULL DEFAULT 0
);
"""


# Columns added after the first release; created on start-up for existing databases.
POST_COLUMNS_ADDED = [
    ("hook", "TEXT"),
    ("pinned_comment", "TEXT"),
    ("mechanic", "TEXT"),
    ("qc", "TEXT"),
    ("auto_approved", "INTEGER NOT NULL DEFAULT 0"),
    ("alt_caption", "TEXT"),
    ("extra_media", "TEXT"),  # carousel: JSON list of {"path", "url", "public_url"} beyond the first image
    ("video_seconds", "INTEGER"),
    ("voice", "INTEGER"),
    ("speech", "TEXT"),  # what she says in a voice reel
]


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
        existing = {r["name"] for r in self.conn.execute("PRAGMA table_info(posts)")}
        with self.conn:
            for column, kind in POST_COLUMNS_ADDED:
                if column not in existing:
                    self.conn.execute(f"ALTER TABLE posts ADD COLUMN {column} {kind}")

    def _post(self, row):
        if row is None:
            return None
        post = Post(dict(row))
        post["targets"] = json.loads(post["targets"])
        post["hashtags"] = json.loads(post["hashtags"] or "[]")
        post["extra_media"] = json.loads(post["extra_media"] or "[]")
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
        if isinstance(fields.get("extra_media"), list):
            fields["extra_media"] = json.dumps(fields["extra_media"])
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

    def auto_approved_count(self, since):
        row = self.conn.execute(
            "SELECT COUNT(*) n FROM posts WHERE auto_approved = 1 AND created_at >= ?", (since.isoformat(),)
        ).fetchone()
        return row["n"]

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
        """Generation spend; chat has its own budget (spent_on)."""
        sql = "SELECT COALESCE(SUM(usd), 0) s FROM costs WHERE ts >= ? AND kind != 'chat'"
        if not include_setup:
            sql += " AND kind NOT LIKE 'setup%'"
        return self.conn.execute(sql, (since.isoformat(),)).fetchone()["s"]

    def spent_on(self, kind, since):
        sql = "SELECT COALESCE(SUM(usd), 0) s FROM costs WHERE ts >= ? AND kind = ?"
        return self.conn.execute(sql, (since.isoformat(), kind)).fetchone()["s"]

    def spent_last_week(self):
        return self.spent(utcnow() - timedelta(days=7))

    # ---------- Fanvue ----------

    def add_fanvue_media(self, post_id, media_uuid, purpose, batch, description, fanvue_post_uuid=None, publish_at=None):
        with self.conn:
            self.conn.execute(
                """INSERT INTO fanvue_media(post_id, media_uuid, purpose, batch, description, fanvue_post_uuid, publish_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (post_id, media_uuid, purpose, batch, description, fanvue_post_uuid, publish_at, utcnow().isoformat()),
            )

    def fanvue_media(self, purpose=None, batch=None):
        sql, args = "SELECT * FROM fanvue_media WHERE 1 = 1", []
        if purpose:
            sql += " AND purpose = ?"
            args.append(purpose)
        if batch:
            sql += " AND batch = ?"
            args.append(batch)
        return [dict(r) for r in self.conn.execute(sql + " ORDER BY id", args)]

    def chat_seen(self, fan_uuid):
        row = self.conn.execute("SELECT message_uuid FROM chat_seen WHERE fan_uuid = ?", (fan_uuid,)).fetchone()
        return row["message_uuid"] if row else None

    def set_chat_seen(self, fan_uuid, message_uuid):
        with self.conn:
            self.conn.execute(
                "INSERT INTO chat_seen(fan_uuid, message_uuid) VALUES (?, ?) "
                "ON CONFLICT(fan_uuid) DO UPDATE SET message_uuid = excluded.message_uuid",
                (fan_uuid, message_uuid),
            )

    def add_draft(self, fan_uuid, fan_name, text, offer_media_uuid, offer_price_cents, reason, status):
        with self.conn:
            cur = self.conn.execute(
                """INSERT INTO chat_drafts(fan_uuid, fan_name, text, offer_media_uuid, offer_price_cents, reason, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (fan_uuid, fan_name, text, offer_media_uuid, offer_price_cents, reason, status, utcnow().isoformat()),
            )
        return cur.lastrowid

    def draft(self, draft_id=None, tg_message_id=None):
        if tg_message_id is not None:
            row = self.conn.execute("SELECT * FROM chat_drafts WHERE tg_message_id = ?", (tg_message_id,)).fetchone()
        else:
            row = self.conn.execute("SELECT * FROM chat_drafts WHERE id = ?", (draft_id,)).fetchone()
        return dict(row) if row else None

    def update_draft(self, draft_id, **fields):
        sets = ", ".join(f"{k} = ?" for k in fields)
        with self.conn:
            self.conn.execute(f"UPDATE chat_drafts SET {sets} WHERE id = ?", [*fields.values(), draft_id])

    def draft_counts(self, since):
        rows = self.conn.execute(
            "SELECT status, COUNT(*) n FROM chat_drafts WHERE created_at >= ? GROUP BY status", (since.isoformat(),)
        )
        return {r["status"]: r["n"] for r in rows}

    def add_offer(self, fan_uuid, media_uuid, price_cents):
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO offers(fan_uuid, media_uuid, price_cents, ts) VALUES (?, ?, ?, ?)",
                (fan_uuid, media_uuid, price_cents, utcnow().isoformat()),
            )

    def offered_to(self, fan_uuid):
        return {r["media_uuid"] for r in self.conn.execute("SELECT media_uuid FROM offers WHERE fan_uuid = ?", (fan_uuid,))}

    def add_swipe(self, text):
        with self.conn:
            return self.conn.execute("INSERT INTO swipes(text, ts) VALUES (?, ?)", (text, utcnow().isoformat())).lastrowid

    def swipe(self, swipe_id):
        row = self.conn.execute("SELECT id, text, used FROM swipes WHERE id = ?", (swipe_id,)).fetchone()
        return dict(row) if row else None

    def swipes(self, limit=10):
        rows = self.conn.execute("SELECT id, text FROM swipes WHERE used = 0 ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    def mark_swipes_used(self, ids):
        with self.conn:
            self.conn.executemany("UPDATE swipes SET used = 1 WHERE id = ?", [(i,) for i in ids])

    def add_fan_request(self, fan_uuid, text):
        with self.conn:
            self.conn.execute("INSERT INTO fan_requests(fan_uuid, text, ts) VALUES (?, ?, ?)", (fan_uuid, text, utcnow().isoformat()))

    def fan_requests(self, limit=15):
        rows = self.conn.execute("SELECT id, text FROM fan_requests WHERE used = 0 ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    def mark_requests_used(self, ids):
        with self.conn:
            self.conn.executemany("UPDATE fan_requests SET used = 1 WHERE id = ?", [(i,) for i in ids])

    def kv_get(self, key, default=None):
        row = self.conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def kv_set(self, key, value):
        with self.conn:
            self.conn.execute(
                "INSERT INTO kv(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value, ensure_ascii=False)),
            )
