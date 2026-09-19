"""SQLite persistence for browser sessions, shared analysis records and saved flow choices."""

from __future__ import annotations

import contextlib
import dataclasses
import json
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)
_DEFAULT_PATH = Path(__file__).resolve().parent.parent / ".data" / "store.db"
_IN_CLAUSE_LIMIT = 500
_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        state TEXT NOT NULL DEFAULT '',
        csrf TEXT NOT NULL DEFAULT '',
        user_id TEXT NOT NULL DEFAULT '',
        user_name TEXT NOT NULL DEFAULT '',
        token_json TEXT NOT NULL DEFAULT '',
        token_expires REAL NOT NULL DEFAULT 0,
        expires REAL NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS analyses (
        track_id TEXT PRIMARY KEY,
        record_json TEXT NOT NULL,
        updated_at REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS preferences (
        user_id TEXT PRIMARY KEY,
        options_json TEXT NOT NULL,
        updated_at REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS jobs (
        playlist_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        name TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'queued',
        priority INTEGER NOT NULL DEFAULT 10,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL,
        PRIMARY KEY (playlist_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS analysis_state (
        playlist_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL DEFAULT '',
        snapshot_id TEXT NOT NULL DEFAULT '',
        view_json TEXT NOT NULL,
        updated_at REAL NOT NULL
    )
    """,
)


class SessionRow(NamedTuple):
    """One durable browser session, including the server-side OAuth token."""

    session_id: str
    state: str
    csrf: str
    user_id: str
    user_name: str
    token_json: str
    token_expires: float
    expires: float


@dataclasses.dataclass
class _State:
    """The shared database path and its single open connection."""

    path: Path = _DEFAULT_PATH
    connection: sqlite3.Connection | None = None


_state = _State()
_lock = threading.RLock()


def configure(path: str | Path) -> None:
    """Point the store at another database file and drop the open connection."""
    with _lock:
        if _state.connection is not None:
            _state.connection.close()
            _state.connection = None
        _state.path = Path(path)


def close() -> None:
    """Close the shared connection so a later call reconnects."""
    configure(_state.path)


def _database() -> sqlite3.Connection:
    """Open the shared connection once and apply the current schema."""
    with _lock:
        if _state.connection is None:
            _state.path = Path(os.environ["SQLITE_PATH"]) if os.environ.get("SQLITE_PATH") else _state.path
            _state.connection = _open(_state.path)
        return _state.connection


def _open(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Bounded waits so a contended or stalled database fails fast instead of hanging requests.
    connection = sqlite3.connect(path, timeout=2.0, check_same_thread=False)
    connection.execute("PRAGMA busy_timeout=2000")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    for statement in _STATEMENTS:
        connection.execute(statement)
    connection.commit()
    with contextlib.suppress(OSError):
        path.chmod(0o600)
    return connection


def save_session(row: SessionRow) -> None:
    """Insert or replace one browser session row."""
    with _lock:
        connection = _database()
        with connection:
            connection.execute(
                "INSERT OR REPLACE INTO sessions"
                " (session_id, state, csrf, user_id, user_name, token_json, token_expires, expires)"
                " VALUES (?,?,?,?,?,?,?,?)",
                tuple(row),
            )


def load_session(session_id: str) -> SessionRow | None:
    """Return the session row for this cookie, or None when absent."""
    with _lock:
        row = (
            _database()
            .execute(
                "SELECT"
                " session_id, state, csrf, user_id, user_name, token_json, token_expires, expires"
                " FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            .fetchone()
        )
    return SessionRow(*row) if row is not None else None


def delete_session(session_id: str | None) -> None:
    """Forget one browser session row, if present."""
    if not session_id:
        return
    with _lock:
        connection = _database()
        with connection:
            connection.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))


def newest_session_id(user_id: str, now: float) -> str | None:
    """Return this listener's newest live session id, for rebuilding queued work after a reload."""
    with _lock:
        row = (
            _database()
            .execute(
                "SELECT session_id FROM sessions"
                " WHERE user_id = ? AND expires >= ?"
                " ORDER BY token_expires DESC LIMIT 1",
                (user_id, now),
            )
            .fetchone()
        )
    return str(row[0]) if row is not None else None


def delete_expired(now: float) -> None:
    """Forget session rows past their expiry time."""
    with _lock:
        connection = _database()
        with connection:
            connection.execute("DELETE FROM sessions WHERE expires < ?", (now,))


def count_sessions() -> int:
    """Count every durable session row."""
    with _lock:
        row = _database().execute("SELECT count(*) FROM sessions").fetchone()
    return int(row[0]) if row is not None else 0


def get_preferences(user_id: str) -> dict[str, object] | None:
    """Return this listener's saved flow choices, or None before the first save."""
    with _lock:
        row = _database().execute("SELECT options_json FROM preferences WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    try:
        options = json.loads(str(row[0]))
    except ValueError:
        return None
    if isinstance(options, dict):
        return {str(key): value for key, value in options.items()}
    return None


def save_preferences(user_id: str, options: dict[str, object]) -> None:
    """Remember this listener's flow choices for the next visit."""
    with _lock:
        connection = _database()
        with connection:
            connection.execute(
                "INSERT OR REPLACE INTO preferences (user_id, options_json, updated_at) VALUES (?,?,?)",
                (user_id, json.dumps(options), time.time()),
            )


class JobRow(NamedTuple):
    """One queued or running playlist analysis in the durable queue."""

    playlist_id: str
    user_id: str
    name: str
    status: str
    priority: int
    created_at: float
    updated_at: float


class AnalysisState(NamedTuple):
    """The last completed analysis for one playlist, kept so revisits can view it instantly."""

    playlist_id: str
    user_id: str
    snapshot_id: str
    view_json: str


def cache_meta() -> dict[str, str] | None:
    """Return the cache version header, or None before the first write."""
    with _lock:
        rows = _database().execute("SELECT key, value FROM meta").fetchall()
    header = {str(key): str(value) for key, value in rows}
    return header or None


def cache_records(track_ids: list[str] | None = None) -> dict[str, str]:
    """Return stored analysis records as raw JSON, optionally only these track ids."""
    with _lock:
        if track_ids is None:
            rows = _database().execute("SELECT track_id, record_json FROM analyses").fetchall()
        else:
            rows = []
            for start in range(0, len(track_ids), _IN_CLAUSE_LIMIT):
                chunk = track_ids[start : start + _IN_CLAUSE_LIMIT]
                marks = ",".join("?" * len(chunk))
                rows.extend(
                    _database()
                    .execute(
                        f"SELECT track_id, record_json FROM analyses WHERE track_id IN ({marks})",  # noqa: S608
                        chunk,
                    )
                    .fetchall()
                )
    return {str(track_id): str(record_json) for track_id, record_json in rows}


def save_cache_records(records: dict[str, str]) -> None:
    """Upsert analysis records keyed by Spotify track id."""
    with _lock:
        connection = _database()
        with connection:
            connection.executemany(
                "INSERT OR REPLACE INTO analyses (track_id, record_json, updated_at) VALUES (?,?,?)",
                ((track_id, record_json, time.time()) for track_id, record_json in records.items()),
            )


def reset_cache(header: dict[str, str], records: dict[str, str]) -> None:
    """Replace the version header and the entire record set in one transaction."""
    with _lock:
        connection = _database()
        with connection:
            connection.execute("DELETE FROM analyses")
            connection.execute("DELETE FROM meta")
            connection.executemany("INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)", header.items())
            connection.executemany(
                "INSERT OR REPLACE INTO analyses (track_id, record_json, updated_at) VALUES (?,?,?)",
                ((track_id, record_json, time.time()) for track_id, record_json in records.items()),
            )


def save_job(row: JobRow) -> None:
    """Insert or replace one durable queue row."""
    with _lock:
        connection = _database()
        with connection:
            connection.execute(
                "INSERT OR REPLACE INTO jobs"
                " (playlist_id, user_id, name, status, priority, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                tuple(row),
            )


def load_job(playlist_id: str, user_id: str) -> JobRow | None:
    """Return one durable queue row, or None when absent."""
    with _lock:
        row = (
            _database()
            .execute(
                "SELECT playlist_id, user_id, name, status, priority, created_at, updated_at"
                " FROM jobs WHERE playlist_id = ? AND user_id = ?",
                (playlist_id, user_id),
            )
            .fetchone()
        )
    return JobRow(*row) if row is not None else None


def queue_rows() -> list[JobRow]:
    """Return every durable queue row, queued before running, each in submission order."""
    with _lock:
        rows = (
            _database()
            .execute(
                "SELECT playlist_id, user_id, name, status, priority, created_at, updated_at FROM jobs"
                " ORDER BY priority, created_at"
            )
            .fetchall()
        )
    return [JobRow(*row) for row in rows]


def delete_job(playlist_id: str, user_id: str) -> None:
    """Forget one durable queue row after its analysis finishes or loses its owner."""
    with _lock:
        connection = _database()
        with connection:
            connection.execute("DELETE FROM jobs WHERE playlist_id = ? AND user_id = ?", (playlist_id, user_id))


def save_analysis(state: AnalysisState) -> None:
    """Keep the last completed analysis for one playlist so revisits view it instantly."""
    with _lock:
        connection = _database()
        with connection:
            connection.execute(
                "INSERT OR REPLACE INTO analysis_state"
                " (playlist_id, user_id, snapshot_id, view_json, updated_at) VALUES (?,?,?,?,?)",
                (*state[:4], time.time()),
            )


def load_analysis(playlist_id: str) -> AnalysisState | None:
    """Return the last completed analysis for this playlist, or None before the first one."""
    with _lock:
        row = (
            _database()
            .execute(
                "SELECT playlist_id, user_id, snapshot_id, view_json FROM analysis_state WHERE playlist_id = ?",
                (playlist_id,),
            )
            .fetchone()
        )
    return AnalysisState(*row) if row is not None else None


def delete_analysis(playlist_id: str) -> None:
    """Forget this playlist's stored analysis so the next visit analyzes it again."""
    with _lock:
        connection = _database()
        with connection:
            connection.execute("DELETE FROM analysis_state WHERE playlist_id = ?", (playlist_id,))


def wipe() -> None:
    """Remove every row, for tests that need a clean database."""
    with _lock:
        connection = _database()
        with connection:
            for statement in (
                "DELETE FROM sessions",
                "DELETE FROM analyses",
                "DELETE FROM meta",
                "DELETE FROM preferences",
                "DELETE FROM jobs",
                "DELETE FROM analysis_state",
            ):
                connection.execute(statement)
