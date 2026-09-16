"""Tiny SQLite store of processed episodes. Committed back to the repo by the workflow."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "state" / "seen.sqlite"


@contextmanager
def connect():
    DB_PATH.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute(
        """CREATE TABLE IF NOT EXISTS episodes (
               guid TEXT PRIMARY KEY,
               podcast TEXT, title TEXT, published TEXT,
               transcript_source TEXT, status TEXT, processed_at TEXT
           )"""
    )
    try:
        yield con
        con.commit()
    finally:
        con.close()


def is_seen(con, guid: str) -> bool:
    return con.execute("SELECT 1 FROM episodes WHERE guid=?", (guid,)).fetchone() is not None


def mark(con, ep, source: str, status: str):
    con.execute(
        "INSERT OR REPLACE INTO episodes VALUES (?,?,?,?,?,?,?)",
        (ep.guid, ep.podcast, ep.title, ep.published.isoformat() if ep.published else None,
         source, status, datetime.now(timezone.utc).isoformat()),
    )
