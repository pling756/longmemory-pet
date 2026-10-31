"""SQLite persistence: messages, memories (with FTS5), and the user profile.

One short-lived connection per operation keeps the class safe to call from the
Qt worker thread while the UI reads stats in the main thread.
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from .models import Memory
from .tokenize import plain_terms, search_text

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  REAL NOT NULL,
    meta        TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);

CREATE TABLE IF NOT EXISTS memories (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    kind           TEXT NOT NULL,
    content        TEXT NOT NULL,
    keywords       TEXT NOT NULL DEFAULT '',
    importance     REAL NOT NULL DEFAULT 0.5,
    created_at     REAL NOT NULL,
    updated_at     REAL NOT NULL,
    last_access_at REAL,
    access_count   INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'active',
    superseded_by  INTEGER,
    source_ids     TEXT NOT NULL DEFAULT '[]',
    search_text    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(status, kind);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    search_text,
    content='memories',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, search_text) VALUES (new.id, new.search_text);
END;
CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, search_text)
    VALUES ('delete', old.id, old.search_text);
END;
CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE OF search_text ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, search_text)
    VALUES ('delete', old.id, old.search_text);
    INSERT INTO memories_fts(rowid, search_text) VALUES (new.id, new.search_text);
END;

CREATE TABLE IF NOT EXISTS profile (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at REAL NOT NULL
);
"""


class MemoryStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    # ------------------------------------------------------------- plumbing
    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init(self) -> None:
        with self._conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)
            memory_count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            fts_count = conn.execute("SELECT COUNT(*) FROM memories_fts").fetchone()[0]
            if memory_count != fts_count:
                conn.execute("INSERT INTO memories_fts(memories_fts) VALUES('rebuild')")

    @staticmethod
    def _row(row: sqlite3.Row) -> Memory:
        def _json_list(value: str | None) -> list:
            try:
                data = json.loads(value or "[]")
                return data if isinstance(data, list) else []
            except json.JSONDecodeError:
                return []

        return Memory(
            id=row["id"],
            kind=row["kind"],
            content=row["content"],
            keywords=[str(k) for k in _json_list(row["keywords"])],
            importance=float(row["importance"]),
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
            last_access_at=row["last_access_at"],
            access_count=int(row["access_count"]),
            status=row["status"],
            superseded_by=row["superseded_by"],
            source_ids=[int(i) for i in _json_list(row["source_ids"])],
        )

    # ------------------------------------------------------------- memories
    def add_memory(
        self,
        kind: str,
        content: str,
        *,
        keywords: Sequence[str] = (),
        importance: float = 0.5,
        created_at: float | None = None,
        source_ids: Sequence[int] = (),
    ) -> int:
        now = time.time()
        created = float(created_at or now)
        search = search_text(content, " ".join(keywords))
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO memories
                    (kind, content, keywords, importance, created_at, updated_at,
                     source_ids, search_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    kind,
                    content.strip(),
                    json.dumps(list(keywords), ensure_ascii=False),
                    max(0.0, min(1.0, float(importance))),
                    created,
                    now,
                    json.dumps(list(source_ids)),
                    search,
                ),
            )
            return int(cur.lastrowid)

    def get_memory(self, memory_id: int) -> Memory | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
        return self._row(row) if row else None

    def get_memories(self, ids: Sequence[int]) -> dict[int, Memory]:
        ids = [int(i) for i in ids]
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM memories WHERE id IN ({placeholders})", ids
            ).fetchall()
        return {int(row["id"]): self._row(row) for row in rows}

    def list_memories(
        self,
        *,
        kind: str | None = None,
        status: str | None = "active",
        limit: int = 300,
        offset: int = 0,
    ) -> list[Memory]:
        clauses: list[str] = []
        args: list[object] = []
        if kind:
            clauses.append("kind=?")
            args.append(kind)
        if status:
            clauses.append("status=?")
            args.append(status)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (
            f"SELECT * FROM memories {where} "
            "ORDER BY importance DESC, created_at DESC LIMIT ? OFFSET ?"
        )
        args.extend([limit, offset])
        with self._conn() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [self._row(row) for row in rows]

    def search_fts(self, query: str, limit: int = 80) -> list[tuple[int, float]]:
        from .tokenize import match_query

        match = match_query(query)
        if not match:
            return []
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT m.id AS id, bm25(memories_fts) AS score
                FROM memories_fts
                JOIN memories m ON m.id = memories_fts.rowid
                WHERE memories_fts MATCH ? AND m.status='active'
                ORDER BY score
                LIMIT ?
                """,
                (match, limit),
            ).fetchall()
        return [(int(r["id"]), float(r["score"])) for r in rows]

    def search_like(self, query: str, limit: int = 60) -> list[tuple[int, float]]:
        """Fallback for very short queries that FTS cannot segment usefully."""
        terms = plain_terms(query)
        if not terms:
            return []
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, content, keywords, importance FROM memories "
                "WHERE status='active' ORDER BY created_at DESC LIMIT 800"
            ).fetchall()
        scored: list[tuple[int, float]] = []
        lowered = query.strip().lower()
        for row in rows:
            haystack = (row["content"] + " " + row["keywords"]).lower()
            if lowered and lowered in haystack:
                scored.append((int(row["id"]), 1.0))
                continue
            hits = sum(1 for term in terms if term.lower() in haystack)
            if hits:
                scored.append((int(row["id"]), min(0.95, hits / max(3, len(terms)))))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]

    def recent_memories(self, limit: int = 8, days: int = 14) -> list[Memory]:
        since = time.time() - days * 86400
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM memories WHERE status='active' AND created_at>=? "
                "ORDER BY created_at DESC LIMIT ?",
                (since, limit),
            ).fetchall()
        return [self._row(row) for row in rows]

    def dedupe_candidates(self, kind: str, limit: int = 250) -> list[Memory]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM memories WHERE status='active' AND kind=? "
                "ORDER BY created_at DESC LIMIT ?",
                (kind, limit),
            ).fetchall()
        return [self._row(row) for row in rows]

    def touch(self, ids: Iterable[int]) -> None:
        ids = list(ids)
        if not ids:
            return
        now = time.time()
        with self._conn() as conn:
            conn.executemany(
                "UPDATE memories SET last_access_at=?, access_count=access_count+1 "
                "WHERE id=?",
                [(now, int(i)) for i in ids],
            )

    def reinforce(self, memory_id: int, importance: float) -> None:
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                "UPDATE memories SET importance=MAX(importance, ?), "
                "last_access_at=?, access_count=access_count+1, updated_at=? "
                "WHERE id=?",
                (max(0.0, min(1.0, importance)), now, now, memory_id),
            )

    def set_importance(self, memory_id: int, importance: float) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE memories SET importance=?, updated_at=? WHERE id=?",
                (max(0.0, min(1.0, importance)), time.time(), memory_id),
            )

    def archive_memory(self, memory_id: int, superseded_by: int | None = None) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE memories SET status='archived', superseded_by=?, updated_at=? "
                "WHERE id=?",
                (superseded_by, time.time(), memory_id),
            )

    def delete_memory(self, memory_id: int) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))

    def active_episodes_before(self, before_ts: float, limit: int = 80) -> list[Memory]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM memories WHERE status='active' AND kind='episode' "
                "AND created_at<? ORDER BY created_at ASC LIMIT ?",
                (before_ts, limit),
            ).fetchall()
        return [self._row(row) for row in rows]

    def count_active_episodes_before(self, before_ts: float) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE status='active' "
                "AND kind='episode' AND created_at<?",
                (before_ts,),
            ).fetchone()
        return int(row[0])

    def decay(self, *, now: float | None = None) -> int:
        """Erode unused memories; archive the ones that fall below the floor.

        Access reinforces a memory; pure passage of time does not delete recent
        important things. Returns the number of archived rows.
        """
        now = now if now is not None else time.time()
        archived = 0
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM memories WHERE status='active'").fetchall()
            for row in rows:
                memory = self._row(row)
                if memory.importance >= 0.85:
                    continue
                idle = memory.idle_days(now)
                if idle < 21:
                    continue
                decayed = memory.importance * (0.5 ** (idle / 120.0))
                if decayed < 0.12 and idle > 120:
                    conn.execute(
                        "UPDATE memories SET status='archived', importance=?, updated_at=? "
                        "WHERE id=?",
                        (decayed, now, memory.id),
                    )
                    archived += 1
                elif decayed < memory.importance - 0.01:
                    conn.execute(
                        "UPDATE memories SET importance=?, updated_at=? WHERE id=?",
                        (decayed, now, memory.id),
                    )
        return archived

    # ------------------------------------------------------------- messages
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        meta: dict | None = None,
    ) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO messages(session_id, role, content, created_at, meta) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    session_id,
                    role,
                    content,
                    time.time(),
                    json.dumps(meta or {}, ensure_ascii=False),
                ),
            )
            return int(cur.lastrowid)

    def recent_messages(self, limit: int = 12, session_id: str | None = None) -> list[dict]:
        args: list[object] = []
        where = ""
        if session_id:
            where = "WHERE session_id=?"
            args.append(session_id)
        args.append(limit)
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM messages {where} ORDER BY id DESC LIMIT ?", args
            ).fetchall()
        messages = [
            {
                "id": int(r["id"]),
                "role": r["role"],
                "content": r["content"],
                "created_at": float(r["created_at"]),
                "meta": json.loads(r["meta"] or "{}"),
            }
            for r in reversed(rows)
        ]
        return messages

    def message_count(self) -> int:
        with self._conn() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0])

    # -------------------------------------------------------------- profile
    def profile(self) -> dict[str, str]:
        with self._conn() as conn:
            rows = conn.execute("SELECT key, value FROM profile ORDER BY key").fetchall()
        return {str(r["key"]): str(r["value"]) for r in rows}

    def set_profile(self, key: str, value: str) -> None:
        key = key.strip()[:40]
        value = value.strip()[:200]
        if not key or not value:
            return
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO profile(key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                "updated_at=excluded.updated_at",
                (key, value, time.time()),
            )

    def delete_profile(self, key: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM profile WHERE key=?", (key,))

    # ---------------------------------------------------------------- stats
    def stats(self) -> dict:
        with self._conn() as conn:
            by_kind = {
                str(r["kind"]): int(r["n"])
                for r in conn.execute(
                    "SELECT kind, COUNT(*) AS n FROM memories WHERE status='active' "
                    "GROUP BY kind"
                ).fetchall()
            }
            active = int(
                conn.execute(
                    "SELECT COUNT(*) FROM memories WHERE status='active'"
                ).fetchone()[0]
            )
            archived = int(
                conn.execute(
                    "SELECT COUNT(*) FROM memories WHERE status='archived'"
                ).fetchone()[0]
            )
            messages = int(conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0])
        try:
            size_kb = self.path.stat().st_size // 1024
        except OSError:
            size_kb = 0
        return {
            "active": active,
            "archived": archived,
            "by_kind": by_kind,
            "messages": messages,
            "db_kb": size_kb,
        }
