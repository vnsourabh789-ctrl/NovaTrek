"""SQLite persistence for saved missions (zero setup, WAL mode)."""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager

from novatrek.config import get_settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trips (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    destination TEXT NOT NULL,
    days INTEGER NOT NULL,
    total_cost REAL NOT NULL,
    created_at REAL NOT NULL,
    data TEXT NOT NULL,
    chat TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_trips_created ON trips(created_at DESC);
"""


@contextmanager
def _conn():
    path = get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init() -> None:
    with _conn() as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(_SCHEMA)


def save_trip(trip: dict) -> None:
    with _conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO trips "
            "(id,title,destination,days,total_cost,created_at,data) VALUES (?,?,?,?,?,?,?)",
            (
                trip["id"],
                trip["title"],
                trip["destination"]["name"] if trip.get("destination") else "",
                trip["intent"]["days"],
                trip["budget"]["total"],
                trip["created_at"],
                json.dumps(trip, ensure_ascii=False),
            ),
        )


def list_trips(limit: int = 50) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT id,title,destination,days,total_cost,created_at "
            "FROM trips ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_trip(trip_id: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT data, chat FROM trips WHERE id=?", (trip_id,)
        ).fetchone()
    if row is None:
        return None
    trip = json.loads(row["data"])
    trip["chat"] = json.loads(row["chat"])
    return trip


def delete_trip(trip_id: str) -> bool:
    with _conn() as con:
        cur = con.execute("DELETE FROM trips WHERE id=?", (trip_id,))
        return cur.rowcount > 0


def append_chat(trip_id: str, role: str, text: str) -> None:
    with _conn() as con:
        row = con.execute("SELECT chat FROM trips WHERE id=?", (trip_id,)).fetchone()
        if row is None:
            return
        chat = json.loads(row["chat"])
        chat.append({"role": role, "text": text, "ts": time.time()})
        con.execute(
            "UPDATE trips SET chat=? WHERE id=?",
            (json.dumps(chat[-40:], ensure_ascii=False), trip_id),
        )
