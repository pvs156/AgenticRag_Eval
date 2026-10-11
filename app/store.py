"""SQLite persistence: sessions, append-only audit events, feedback, mock cases and handoffs.

SQLite on a mounted volume is enough for a single-instance demo (backed up nightly, see deploy/). Swapping to
Postgres would only change this module.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at REAL NOT NULL, state TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, session_id TEXT, trace_id TEXT,
  kind TEXT NOT NULL, detail TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, session_id TEXT, trace_id TEXT,
  rating INTEGER NOT NULL, comment TEXT
);
CREATE TABLE IF NOT EXISTS cases (
  id TEXT PRIMARY KEY, ts TEXT NOT NULL, session_id TEXT NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL
);
"""
SESSION_TTL_S = 24 * 3600


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, path: str | None = None):
        url = path or get_settings().database_url
        db_path = url.removeprefix("sqlite:///")
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)

    def _exec(self, sql: str, args: tuple = ()) -> list[tuple]:
        with self._lock:
            cur = self._db.execute(sql, args)
            self._db.commit()
            return cur.fetchall()

    # sessions -----------------------------------------------------------------
    def get_session(self, sid: str) -> dict | None:
        rows = self._exec("SELECT state, updated_at FROM sessions WHERE id = ?", (sid,))
        if not rows or time.time() - rows[0][1] > SESSION_TTL_S:
            return None
        return json.loads(rows[0][0])

    def save_session(self, sid: str, state: dict) -> None:
        self._exec(
            "INSERT INTO sessions (id, created_at, updated_at, state) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at, state = excluded.state",
            (sid, _now(), time.time(), json.dumps(state, default=str)),
        )

    def purge(self, older_than_days: int = 30) -> None:
        cutoff = time.time() - older_than_days * 86400
        self._exec("DELETE FROM sessions WHERE updated_at < ?", (cutoff,))

    # audit / feedback / cases --------------------------------------------------
    def audit(self, kind: str, detail: dict, session_id: str | None = None, trace_id: str | None = None) -> None:
        self._exec(
            "INSERT INTO audit_events (ts, session_id, trace_id, kind, detail) VALUES (?, ?, ?, ?, ?)",
            (_now(), session_id, trace_id, kind, json.dumps(detail, default=str)),
        )

    def feedback(self, session_id: str | None, trace_id: str | None, rating: int, comment: str | None) -> None:
        self._exec(
            "INSERT INTO feedback (ts, session_id, trace_id, rating, comment) VALUES (?, ?, ?, ?, ?)",
            (_now(), session_id, trace_id, rating, comment),
        )

    def create_case(self, session_id: str, kind: str, detail: dict) -> str:
        cid = f"{kind[:3].upper()}-{uuid.uuid4().hex[:8].upper()}"
        self._exec(
            "INSERT INTO cases (id, ts, session_id, kind, detail) VALUES (?, ?, ?, ?, ?)",
            (cid, _now(), session_id, kind, json.dumps(detail, default=str)),
        )
        return cid

    def audit_trail(self, session_id: str) -> list[dict]:
        rows = self._exec(
            "SELECT ts, trace_id, kind, detail FROM audit_events WHERE session_id = ? ORDER BY id", (session_id,)
        )
        return [{"ts": r[0], "trace_id": r[1], "kind": r[2], "detail": json.loads(r[3])} for r in rows]
