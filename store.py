import array
import os
import re
import sqlite3
import time

from embeddings import get_embedder

DB_PATH = os.environ.get("MEMORY_DB", "memory.db")
MIN_SCORE = 0.1

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories(
    id INTEGER PRIMARY KEY,
    project TEXT NOT NULL,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    created REAL NOT NULL,
    useful INTEGER DEFAULT 0,
    embedding BLOB,
    embedder TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS mem_fts USING fts5(content, tokenize='porter');
CREATE TABLE IF NOT EXISTS events(
    id INTEGER PRIMARY KEY,
    project TEXT NOT NULL,
    type TEXT NOT NULL,
    text TEXT NOT NULL,
    ts REAL NOT NULL
);
"""


def _pack(vec):
    return array.array("f", vec).tobytes()


def _unpack(blob):
    arr = array.array("f")
    arr.frombytes(blob)
    return list(arr)


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


class MemoryStore:
    def __init__(self, path=None):
        self.db = sqlite3.connect(path or os.environ.get("MEMORY_DB", DB_PATH))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        cols = {r["name"] for r in self.db.execute("PRAGMA table_info(memories)")}
        for col, ddl in (("embedding", "BLOB"), ("embedder", "TEXT")):
            if col not in cols:
                self.db.execute(f"ALTER TABLE memories ADD COLUMN {col} {ddl}")
        self.db.commit()
        self.embedder = get_embedder()

    def add(self, project, kind, content):
        content = content.strip()
        dup = self.db.execute(
            "SELECT id FROM memories WHERE project=? AND content=?", (project, content)
        ).fetchone()
        if dup:
            return dup["id"], False
        vec = self.embedder.embed(content)
        cur = self.db.execute(
            "INSERT INTO memories(project, kind, content, created, embedding, embedder)"
            " VALUES (?,?,?,?,?,?)",
            (project, kind, content, time.time(), _pack(vec), self.embedder.name),
        )
        self.db.execute(
            "INSERT INTO mem_fts(rowid, content) VALUES (?,?)", (cur.lastrowid, content)
        )
        self.db.commit()
        return cur.lastrowid, True

    def _vector(self, row):
        if row["embedding"] is not None and row["embedder"] == self.embedder.name:
            return _unpack(row["embedding"])
        vec = self.embedder.embed(row["content"])
        self.db.execute(
            "UPDATE memories SET embedding=?, embedder=? WHERE id=?",
            (_pack(vec), self.embedder.name, row["id"]),
        )
        self.db.commit()
        return vec

    def _keyword_scores(self, project, query):
        words = re.findall(r"[A-Za-z0-9_]{3,}", query)
        if not words:
            return {}
        rows = self.db.execute(
            "SELECT m.id AS id, bm25(mem_fts) AS s FROM mem_fts"
            " JOIN memories m ON m.id = mem_fts.rowid"
            " WHERE mem_fts MATCH ? AND m.project = ?",
            (" OR ".join(words), project),
        ).fetchall()
        return {r["id"]: -r["s"] for r in rows}

    def search(self, project, query, limit=5):
        rows = self.db.execute("SELECT * FROM memories WHERE project=?", (project,)).fetchall()
        if not rows:
            return []
        qvec = self.embedder.embed(query)
        keyword = self._keyword_scores(project, query)
        top = max(keyword.values(), default=0) or 1.0
        scored = []
        for r in rows:
            cos = max(_dot(qvec, self._vector(r)), 0.0)
            kw = max(keyword.get(r["id"], 0.0), 0.0) / top
            score = 0.6 * cos + 0.4 * kw + 0.03 * min(r["useful"], 5)
            if score >= MIN_SCORE:
                item = dict(r)
                item["score"] = round(score, 3)
                item.pop("embedding", None)
                scored.append(item)
        scored.sort(key=lambda m: -m["score"])
        return scored[:limit]

    def list(self, project):
        return self.db.execute(
            "SELECT id, kind, content, useful FROM memories WHERE project=? ORDER BY id", (project,)
        ).fetchall()

    def mark_useful(self, mem_id):
        self.db.execute("UPDATE memories SET useful = useful + 1 WHERE id=?", (mem_id,))
        self.db.commit()

    def forget(self, mem_id):
        self.db.execute("DELETE FROM memories WHERE id=?", (mem_id,))
        self.db.execute("DELETE FROM mem_fts WHERE rowid=?", (mem_id,))
        self.db.commit()

    def reindex(self):
        rows = self.db.execute("SELECT * FROM memories").fetchall()
        for r in rows:
            vec = self.embedder.embed(r["content"])
            self.db.execute(
                "UPDATE memories SET embedding=?, embedder=? WHERE id=?",
                (_pack(vec), self.embedder.name, r["id"]),
            )
        self.db.commit()
        return len(rows)

    def add_event(self, project, etype, text):
        self.db.execute(
            "INSERT INTO events(project, type, text, ts) VALUES (?,?,?,?)",
            (project, etype, text.strip(), time.time()),
        )
        self.db.commit()

    def pop_events(self, project):
        rows = self.db.execute(
            "SELECT type, text FROM events WHERE project=? ORDER BY id", (project,)
        ).fetchall()
        self.db.execute("DELETE FROM events WHERE project=?", (project,))
        self.db.commit()
        return [{"type": r["type"], "text": r["text"]} for r in rows]
