"""FastAPI endpoints and the compiled React app."""

from __future__ import annotations

import json
import logging
import secrets
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock, Thread
from time import perf_counter
from typing import TYPE_CHECKING, Annotated, Any, Literal, cast
from urllib.parse import urlsplit

import spotipy
from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field, ValidationError
from spotipy.exceptions import SpotifyOauthError

from api import store
from api.playlist_sorter import SpotifyPlaylistSorter
from api.spotify_auth import get_all_playlists, get_auth_manager, get_redirect_uri, get_spotify_client, is_configured
from api.youtube import SourceAccessError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from spotipy.oauth2 import SpotifyOAuth

logger = logging.getLogger(__name__)
SESSION_SECONDS = 24 * 60 * 60
LOGIN_SECONDS = 10 * 60
MAX_SESSIONS = 200
REANALYZE_SECONDS = 150.0
# Manual rematches always run before queued playlist analyses.
PRIORITY_REMATCH = 0
PRIORITY_ANALYZE = 10
COOKIE = "playlist_session"
SpotifyId = Annotated[str, Field(pattern=r"^[A-Za-z0-9]{22}$")]


class Recording(BaseModel):
    """The YouTube recording this song's audio was measured from."""

    video_id: str
    title: str | None = None
    channel: str | None = None
    duration_seconds: float | None = None
    confident: bool = False


class Track(BaseModel):
    """One complete playlist entry, including fixed items and missing measurements."""

    occurrence: str
    original_position: int
    id: str | None
    duration_ms: int | None
    kind: str
    fixed_reason: str | None
    analysis_status: Literal["pending", "matching", "downloading", "analyzing", "ready", "uncertain", "error", "fixed"]
    name: str
    artist: str
    key: str | None = None
    bpm: float | None = None
    energy: float | None = None
    recording: Recording | None = None


class Candidate(BaseModel):
    """One searchable YouTube recording a listener could choose for a song."""

    video_id: str
    title: str
    channel: str
    duration_seconds: float | None
    live: bool
    suggested: bool


class ListeningOptions(BaseModel):
    """Plain-language listening choices the arrangement honors."""

    preset: Literal["gentle", "steady", "buildup", "mixed"] = "steady"
    pace: float = Field(default=0.5, ge=0, le=1)
    energy: float = Field(default=0.5, ge=0, le=1)
    variety: float = Field(default=0.5, ge=0, le=1)


class JobView(BaseModel):
    """Public job state; tokens and sorter objects never enter responses."""

    playlist_id: str
    revision: str = Field(default_factory=lambda: secrets.token_urlsafe(16))
    name: str = "Your playlist"
    status: Literal["analyzing", "ready", "sorting", "saving", "saved", "restoring", "restored", "error"] = "analyzing"
    can_restore: bool = False
    completed: int = 0
    total: int = 0
    kept_count: int = 0
    metadata_loaded: bool = False
    analyzed_count: int = 0
    queue_position: int | None = None
    stale: bool = False
    rematching: bool = False
    # Served from the analysis store: true results, but no live playlist data to act on.
    stored: bool = False
    options: ListeningOptions = Field(default_factory=ListeningOptions)
    first_occurrence: str | None = None
    last_occurrence: str | None = None
    placements: dict[str, int] = Field(default_factory=dict)
    arrangement: dict[str, Any] | None = None
    review: dict[str, Any] | None = None
    tracks: list[Track] = Field(default_factory=list)
    sorted_tracks: list[Track] = Field(default_factory=list)
    transitions: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None


@dataclass
class Job:
    """One playlist and preview per session."""

    sorter: SpotifyPlaylistSorter | None
    view: JobView
    user_id: str = ""
    sorted_order: list[str] = field(default_factory=list)

    def invalidate_preview(self, **updates: Any) -> None:  # noqa: ANN401 - pydantic accepts every field value.
        """Own the whole preview field-group: clear it, then apply the caller's overrides."""
        self.view = self.view.model_copy(
            update={
                "sorted_tracks": [],
                "transitions": [],
                "review": None,
                "arrangement": None,
                "first_occurrence": None,
                "last_occurrence": None,
                "placements": {},
                **updates,
            }
        )


@dataclass
class Session:
    """Server-only OAuth state with an opaque browser cookie."""

    auth: SpotifyOAuth
    state: str
    expires: float = field(default_factory=lambda: time.time() + LOGIN_SECONDS)
    csrf: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    user: dict[str, str] = field(default_factory=dict)
    jobs: dict[str, Job] = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock)
    id: str = ""
    token_saved: float = 0.0


class SessionView(BaseModel):
    """The small amount of login state the browser needs."""

    configured: bool
    user: dict[str, str] | None = None
    csrf: str | None = None


class Playlist(BaseModel):
    """An editable Spotify playlist."""

    id: str
    name: str
    total: int
    image: str | None = None


class PreviewRequest(BaseModel):
    """Bind a mutation to the preview this browser actually saw."""

    revision: Annotated[str, Field(min_length=1, max_length=100)]


class SortRequest(PreviewRequest):
    """Select listening options, optional endpoint pins and unanalyzable-item placements."""

    options: ListeningOptions = Field(default_factory=ListeningOptions)
    first_occurrence: Annotated[str, Field(min_length=1, max_length=512)] | None = None
    last_occurrence: Annotated[str, Field(min_length=1, max_length=512)] | None = None
    placements: dict[Annotated[str, Field(min_length=1, max_length=512)], Annotated[int, Field(ge=0)]] = Field(
        default_factory=dict
    )


class MatchRequest(BaseModel):
    """Choose one YouTube recording as the source for a song's audio analysis."""

    video_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{11}$")]


def _lookup_session(request: Request) -> Session | None:
    cookie = request.cookies.get(COOKIE)
    with request.app.state.sessions_lock:
        sessions = cast("dict[str, Session]", request.app.state.sessions)
        for key in list(sessions):
            if sessions[key].expires < time.time():
                del sessions[key]
                store.delete_session(key)
        session = sessions.get(cookie) if cookie else None
    if session is None and cookie:
        session = _hydrate_session(cookie)
        if session is not None:
            with request.app.state.sessions_lock:
                cast("dict[str, Session]", request.app.state.sessions).setdefault(cookie, session)
    return session


def _hydrate_session(session_id: str) -> Session | None:
    """Rebuild a session from SQLite so a server reload keeps the login."""
    row = store.load_session(session_id)
    if row is None or row.expires < time.time():
        store.delete_session(session_id)
        return None
    auth = get_auth_manager(row.state)
    try:
        token = json.loads(row.token_json) if row.token_json else None
    except ValueError:
        token = None
    if isinstance(token, dict):
        auth.cache_handler.save_token_to_cache(token)
    return Session(
        auth=auth,
        state=row.state,
        expires=row.expires,
        csrf=row.csrf,
        user={"id": row.user_id, "name": row.user_name} if row.user_id else {},
        id=session_id,
        token_saved=row.token_expires,
    )


def _sync_token(session: Session) -> None:
    """Persist refreshed OAuth tokens so they survive a server reload."""
    info = session.auth.cache_handler.get_cached_token()
    if session.id and session.user and isinstance(info, dict):
        expires = info.get("expires_at")
        if isinstance(expires, (int, float)) and expires != session.token_saved:
            session.token_saved = float(expires)
            store.save_session(
                store.SessionRow(
                    session.id,
                    session.state,
                    session.csrf,
                    session.user.get("id", ""),
                    session.user.get("name", ""),
                    json.dumps(info),
                    float(expires),
                    session.expires,
                )
            )


def _require_session(request: Request) -> Session:
    session = _lookup_session(request)
    if session is None or not session.user:
        raise HTTPException(401, "Connect Spotify to continue.")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("X-CSRF-Token", "")
        if not secrets.compare_digest(csrf, session.csrf):
            raise HTTPException(403, "Refresh the page and try again.")
    _sync_token(session)
    return session


CurrentSession = Annotated[Session, Depends(_require_session)]


def _set_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        COOKIE,
        session_id,
        max_age=SESSION_SECONDS,
        httponly=True,
        secure=get_redirect_uri().startswith("https://"),
        samesite="lax",
    )


_TRACK_COLUMNS = {
    "Track": "name",
    "Artist": "artist",
    "Camelot": "key",
    "BPM": "bpm",
    "Energy": "energy",
    "Recording": "recording",
}


def _tracks(entries: list[dict[str, Any]]) -> list[Track]:
    """Serialize the entry identities assigned when the source playlist was loaded."""
    return [
        Track.model_validate({_TRACK_COLUMNS.get(key, key): value for key, value in entry.items()}) for entry in entries
    ]


def _analysis_counts(tracks: list[Track]) -> dict[str, int]:
    """Count completed measurements separately from entries that must stay in place."""
    return {
        "analyzed_count": sum(track.analysis_status == "ready" for track in tracks),
        "kept_count": sum(track.fixed_reason is not None for track in tracks),
    }


def _rematch_job(job: Job, occurrence: str, video_id: str, deadline: float, snapshot_id: str) -> None:
    """Reanalyze one occurrence with a listener-chosen recording and refresh the view."""
    sorter = job.sorter
    if sorter is None:
        job.view = job.view.model_copy(update={"status": "error", "error": "Analyze the playlist before continuing."})
        return
    entry = next((item for item in sorter.original_items if item["occurrence"] == occurrence), None)
    known = {track.occurrence for track in job.view.tracks}
    if entry is None or occurrence not in known:
        job.view = job.view.model_copy(update={"status": "error", "error": "This song isn't in the loaded playlist."})
        return
    progress_lock = Lock()

    def record_progress(recording_id: str, result: dict[str, Any]) -> None:
        if recording_id != entry["id"]:
            return
        stage = result.get("status")
        phase = {"matching": "matching", "downloading": "downloading", "analyzing": "analyzing"}.get(
            str(stage), "ready"
        )
        with progress_lock:
            tracks = [
                track.model_copy(update={"analysis_status": phase}) if track.occurrence == occurrence else track
                for track in job.view.tracks
            ]
            job.view = job.view.model_copy(update={"tracks": tracks})

    success, message = sorter.reanalyze_track(entry, video_id, record_progress, deadline=deadline)
    with progress_lock:
        if success:
            tracks = [
                _tracks([item])[0] if item["occurrence"] == occurrence else track
                for item, track in zip(sorter.original_items, job.view.tracks, strict=True)
            ]
            job.invalidate_preview(
                tracks=tracks,
                status="ready",
                error=None,
                revision=secrets.token_urlsafe(16),
                can_restore=sorter.can_restore,
                **_analysis_counts(tracks),
            )
            _record_analysis_state(job, snapshot_id)
        else:
            tracks = [
                track.model_copy(update={"analysis_status": "error", "fixed_reason": message})
                if track.occurrence == occurrence
                else track
                for track in job.view.tracks
            ]
            # A failed rematch marks only that song; the playlist stays usable.
            job.view = job.view.model_copy(
                update={"tracks": tracks, "status": "ready", "error": None, **_analysis_counts(tracks)}
            )


def _analyze_job(job: Job) -> None:
    """Publish complete metadata and serialize parallel recording progress."""
    sorter = job.sorter
    if sorter is None:
        job.view = job.view.model_copy(update={"status": "error", "error": "Analyze the playlist before continuing."})
        return
    progress_lock = Lock()

    def entries_loaded(entries: list[dict[str, Any]]) -> None:
        tracks = _tracks(entries)
        with progress_lock:
            job.view = job.view.model_copy(
                update={
                    "metadata_loaded": True,
                    "tracks": tracks,
                    "name": sorter.playlist_name or "Your playlist",
                    "total": sum(track.analysis_status == "pending" for track in tracks),
                    **_analysis_counts(tracks),
                }
            )

    def record_progress(recording_id: str, result: dict[str, Any]) -> None:
        phase = "fixed" if result["status"] == "unsupported" else result["status"]
        reason = (
            result.get("message", "Couldn't analyze this song") if phase in {"fixed", "uncertain", "error"} else None
        )
        seconds = (result.get("diagnostics") or {}).get("total_seconds")
        if isinstance(seconds, (int, float)) and seconds > 0:
            _RECENT_SECONDS.append(float(seconds))
        with progress_lock:
            finished = (
                sum(
                    track.id == recording_id
                    and track.analysis_status in {"pending", "matching", "downloading", "analyzing"}
                    for track in job.view.tracks
                )
                if phase in {"ready", "uncertain", "error", "fixed"}
                else 0
            )
            tracks = [
                track.model_copy(update={"analysis_status": phase, "fixed_reason": reason})
                if track.id == recording_id and track.analysis_status != "fixed"
                else track
                for track in job.view.tracks
            ]
            job.view = job.view.model_copy(
                update={
                    "tracks": tracks,
                    "completed": job.view.completed + finished,
                    **_analysis_counts(tracks),
                }
            )

    def progress(done: int, total: int) -> None:
        with progress_lock:
            job.view = job.view.model_copy(
                update={"completed": done, "total": total},
            )

    tracks = sorter.load_playlist(
        progress_callback=progress, entries_callback=entries_loaded, record_callback=record_progress
    )
    tracks = _tracks(tracks)
    job.invalidate_preview(
        name=sorter.playlist_name or "Your playlist",
        tracks=tracks,
        metadata_loaded=True,
        completed=job.view.total,
        status="ready",
        **_analysis_counts(tracks),
    )
    _record_analysis_state(job, sorter.snapshot_id or "")


def _run_arrange(job: Job, sorter: SpotifyPlaylistSorter) -> None:
    """Arrange the loaded entries and publish the resulting preview."""
    job.sorted_order = sorter.sort_playlist(
        job.view.options.model_dump(),
        job.view.first_occurrence,
        job.view.last_occurrence,
        job.view.placements,
    )
    if not job.sorted_order:
        job.view = job.view.model_copy(update={"status": "error", "error": "Review your song choices and try again."})
        return
    transitions = sorter.get_transition_analysis(job.sorted_order)
    job.view = job.view.model_copy(
        update={
            "sorted_tracks": _tracks(sorter.proposed_tracks(job.sorted_order)),
            "transitions": transitions,
            "review": sorter.review_summary(job.sorted_order, transitions),
            "arrangement": sorter.arrangement_summary,
            "status": "ready",
        }
    )
    _record_analysis_state(job, sorter.snapshot_id or "")


def _run_restore(job: Job, sorter: SpotifyPlaylistSorter) -> None:
    """Undo only the most recent verified save of this session."""
    success, message = sorter.restore_spotify_playlist()
    job.sorted_order = sorter.current_order.copy() if success else []
    job.invalidate_preview(
        status="restored" if success else "error",
        error=None if success else message,
        can_restore=False,
        sorted_tracks=_tracks(sorter.proposed_tracks(job.sorted_order)),
    )
    if success:
        _record_analysis_state(job, sorter.snapshot_id or "")


def _run_save(job: Job, sorter: SpotifyPlaylistSorter) -> None:
    """Apply only the preview the browser has seen, then verify it on Spotify."""
    success, message = sorter.update_spotify_playlist(job.sorted_order)
    job.view = job.view.model_copy(
        update={
            "status": "saved" if success else "error",
            "error": None if success else message,
            "can_restore": sorter.can_restore,
        }
    )
    if success:
        _record_analysis_state(job, sorter.snapshot_id or "")


def _run_job(job: Job, action: str, release: Callable[[], None]) -> None:
    """Run blocking work in FastAPI's background thread pool."""
    sorter = job.sorter
    try:
        if action == "analyze":
            _analyze_job(job)
        elif action == "sort":
            assert sorter is not None  # noqa: S101 - queued actions always own a loaded playlist.
            _run_arrange(job, sorter)
        elif action == "restore":
            assert sorter is not None  # noqa: S101
            _run_restore(job, sorter)
        else:
            assert sorter is not None  # noqa: S101
            _run_save(job, sorter)
    except Exception:
        logger.exception("Playlist %s failed during %s", job.view.playlist_id, action)
        message = "Something went wrong. Please analyze the playlist again."
        if action in {"save", "restore"}:
            if sorter is not None:
                sorter.invalidate_save()
            job.view = job.view.model_copy(update={"can_restore": False})
            message = "The change couldn't be verified. Some songs may have moved. Analyze the playlist again."
        if action == "analyze":
            _mark_analysis_interrupted(job)
        job.view = job.view.model_copy(update={"status": "error", "error": message})
    finally:
        release()


def _mark_analysis_interrupted(job: Job) -> None:
    """Label every in-flight recording as failed so no pending stage labels remain."""
    tracks = [
        track.model_copy(update={"analysis_status": "error", "fixed_reason": "Analysis interrupted"})
        if track.analysis_status in {"pending", "matching", "downloading", "analyzing"}
        else track
        for track in job.view.tracks
    ]
    job.view = job.view.model_copy(update={"tracks": tracks, **_analysis_counts(tracks)})


@dataclass(order=True)
class QueueItem:
    """One pending analysis unit: a whole playlist, or a single manual rematch first."""

    priority: int
    created_at: float
    action: str
    job: Job = field(compare=False)
    occurrence: str = field(default="", compare=False)
    video_id: str = field(default="", compare=False)
    snapshot_id: str = field(default="", compare=False)


def _record_analysis_state(job: Job, snapshot_id: str) -> None:
    """Keep the finished analysis so revisits can view this playlist without waiting."""
    if not job.user_id or snapshot_id is None:
        return
    try:
        store.save_analysis(
            store.AnalysisState(job.view.playlist_id, job.user_id, snapshot_id, job.view.model_dump_json())
        )
    except Exception:
        logger.exception("Could not store the analysis for playlist %s", job.view.playlist_id)


class QueueEntry(BaseModel):
    """The listener-facing queue line for one pending analysis unit."""

    playlist_id: str
    name: str
    status: Literal["queued", "running"]
    queue_position: int | None
    completed: int
    total: int
    eta_seconds: int | None


# Recent per-recording durations, the basis of the queue page's time estimates.
_RECENT_SECONDS: deque[float] = deque(maxlen=20)


def _eta_seconds(view: JobView) -> int | None:
    """Estimate the seconds left for one unit, or None when no timings are known yet."""
    if not _RECENT_SECONDS:
        return None
    if not view.metadata_loaded:
        return None
    remaining = max(0, view.total - view.completed)
    return round(remaining * (sum(_RECENT_SECONDS) / len(_RECENT_SECONDS)))


def _drain(app: FastAPI) -> None:
    """Run queued analysis units one at a time, highest priority then submission order."""
    while True:
        with app.state.queue_lock:
            if app.state.running is not None or not app.state.queue_items:
                return
            item = app.state.queue_items.pop(0)
            app.state.running = item
        try:
            if item.action == "rematch":
                _run_rematch(item.job, item.occurrence, item.video_id, item.snapshot_id)
            else:
                row = store.load_job(item.job.view.playlist_id, item.job.user_id)
                if row is not None:
                    store.save_job(row._replace(status="running", updated_at=time.time()))
                item.job.view = item.job.view.model_copy(update={"queue_position": None})
                _run_job(item.job, "analyze", lambda: None)
        finally:
            with app.state.queue_lock:
                app.state.running = None
                if item.action == "analyze":
                    store.delete_job(item.job.view.playlist_id, item.job.user_id)
                elif item.action == "rematch" and not any(
                    pending.action == "rematch" and pending.job is item.job for pending in app.state.queue_items
                ):
                    item.job.view = item.job.view.model_copy(update={"rematching": False})


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Keep live session objects in process; SQLite keeps them durable across reloads."""
    app.state.sessions = {}
    app.state.sessions_lock = Lock()
    app.state.queue_items = []
    app.state.running = None
    app.state.queue_lock = Lock()
    store.delete_expired(time.time())
    _reenqueue_durable(app)
    yield
    app.state.sessions.clear()


def _reenqueue_durable(app: FastAPI) -> None:
    """Put playlist analyses that a reload interrupted back into the queue."""
    for durable in store.queue_rows():
        row = durable._replace(status="queued") if durable.status == "running" else durable
        if row.status == "queued" and durable.status == "running":
            store.save_job(row)
        session_id = store.newest_session_id(row.user_id, time.time())
        stored = _hydrate_session(session_id) if session_id else None
        if stored is None or not stored.user:
            store.delete_job(row.playlist_id, row.user_id)
            continue
        job = Job(
            SpotifyPlaylistSorter(row.playlist_id, get_spotify_client(stored.auth)),
            JobView(playlist_id=row.playlist_id, name=row.name or "Your playlist"),
            user_id=row.user_id,
        )
        stored.jobs[row.playlist_id] = job
        with app.state.queue_lock:
            app.state.queue_items.append(
                QueueItem(priority=row.priority, created_at=row.created_at, action="analyze", job=job)
            )
    if any(item.action == "analyze" for item in app.state.queue_items):
        Thread(target=_drain, args=(app,), daemon=True, name="analysis-worker").start()


router = APIRouter()


async def private_responses(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Keep API results out of shared caches."""
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


async def invalid_request(_request: Request, _exc: Exception) -> JSONResponse:
    """Return a short validation message without echoing submitted values."""
    return JSONResponse({"detail": "Review your choice and try again."}, status_code=422)


async def spotify_error(request: Request, exc: Exception) -> JSONResponse:
    """Map Spotify failures to a retry or reconnect message."""
    spotify_status = exc.http_status if isinstance(exc, spotipy.SpotifyException) else None
    logger.warning("Spotify request failed with status %s", spotify_status)
    if spotify_status == status.HTTP_401_UNAUTHORIZED or isinstance(exc, SpotifyOauthError):
        session = _lookup_session(request)
        if session:
            session.user.clear()
            store.delete_session(session.id)
        return JSONResponse({"detail": "Connect Spotify again to continue."}, status_code=401)
    return JSONResponse({"detail": "Spotify couldn't complete that request. Please try again."}, status_code=502)


async def unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
    """Log server failures without returning their internals."""
    logger.error("Request failed", exc_info=exc)
    return JSONResponse({"detail": "Something went wrong. Please try again."}, status_code=500)


@router.get("/api/health")
def health() -> dict[str, str]:
    """Report whether the server is running."""
    return {"status": "ok"}


@router.get("/api/session")
def session_info(request: Request) -> SessionView:
    """Return login state without exposing Spotify tokens."""
    session = _lookup_session(request)
    if session and session.user:
        return SessionView(configured=is_configured(), user=session.user, csrf=session.csrf)
    return SessionView(configured=is_configured())


@router.get("/api/auth/login")
def login(request: Request) -> RedirectResponse:
    """Start a new Spotify login with a unique state value."""
    if not is_configured():
        return RedirectResponse("/?error=setup", status_code=303)
    # Set the session cookie on the same host Spotify will return to.
    if request.url.hostname == "localhost" and urlsplit(get_redirect_uri()).hostname == "127.0.0.1":
        return RedirectResponse(str(request.url.replace(hostname="127.0.0.1")), status_code=303)
    _lookup_session(request)  # Remove expired sessions before admitting a new login.
    store.delete_expired(time.time())
    state = secrets.token_urlsafe(32)
    session = Session(auth=get_auth_manager(state), state=state)
    session_id = secrets.token_urlsafe(32)
    session.id = session_id
    if store.count_sessions() >= MAX_SESSIONS:
        raise HTTPException(503, "We're busy right now. Please try again soon.")
    with request.app.state.sessions_lock:
        old_id = request.cookies.get(COOKIE)
        request.app.state.sessions.pop(old_id, None)
        request.app.state.sessions[session_id] = session
    store.delete_session(old_id)
    store.save_session(store.SessionRow(session_id, state, session.csrf, "", "", "", 0.0, session.expires))
    response = RedirectResponse(session.auth.get_authorize_url(state=state), status_code=303)
    _set_cookie(response, session_id)
    return response


@router.get("/api/auth/callback")
def callback(request: Request, state: str = "", code: str = "", error: str = "") -> RedirectResponse:
    """Consume the login state once and rotate the session cookie."""
    session = _lookup_session(request)
    if not session:
        return RedirectResponse("/?error=login", status_code=303)
    with session.lock:
        if not session.state or not secrets.compare_digest(state, session.state):
            return RedirectResponse("/?error=login", status_code=303)
        session.state = ""
        if error or not code:
            return RedirectResponse("/?error=login", status_code=303)
        try:
            session.auth.get_access_token(code, as_dict=False, check_cache=False)
            profile = get_spotify_client(session.auth).current_user()
            session.user = {"id": profile["id"], "name": profile.get("display_name") or "Spotify listener"}
        except Exception:
            logger.exception("Spotify login failed")
            return RedirectResponse("/?error=login", status_code=303)
        session.expires = time.time() + SESSION_SECONDS
        session_id = secrets.token_urlsafe(32)
        token = session.auth.cache_handler.get_cached_token()
        token_json = json.dumps(token) if isinstance(token, dict) else ""
        token_expires = float(token.get("expires_at") or 0) if isinstance(token, dict) else 0.0
        with request.app.state.sessions_lock:
            old_id = request.cookies.get(COOKIE)
            request.app.state.sessions.pop(old_id, None)
            session.id = session_id
            request.app.state.sessions[session_id] = session
        store.delete_session(old_id)
        store.save_session(
            store.SessionRow(
                session_id,
                "",
                session.csrf,
                session.user["id"],
                session.user["name"],
                token_json,
                token_expires,
                session.expires,
            )
        )
        session.token_saved = token_expires
    response = RedirectResponse("/playlists", status_code=303)
    _set_cookie(response, session_id)
    return response


@router.post("/api/auth/logout")
def logout(request: Request, response: Response, _session: CurrentSession) -> dict[str, bool]:
    """Forget this browser session and expire its cookie."""
    with request.app.state.sessions_lock:
        old_id = request.cookies.get(COOKIE)
        request.app.state.sessions.pop(old_id, None)
    store.delete_session(old_id)
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.get("/api/playlists")
def playlists(session: CurrentSession) -> list[Playlist]:
    """List the playlists this listener can edit."""
    return [Playlist.model_validate(p) for p in get_all_playlists(get_spotify_client(session.auth), session.user["id"])]


@router.get("/api/preferences")
def read_preferences(session: CurrentSession) -> ListeningOptions:
    """Return this listener's saved flow choices, or the defaults before a first save."""
    saved = store.get_preferences(session.user["id"])
    return ListeningOptions.model_validate(saved or {})


@router.put("/api/preferences")
def update_preferences(options: ListeningOptions, session: CurrentSession) -> ListeningOptions:
    """Remember this listener's flow choices for future visits."""
    store.save_preferences(session.user["id"], options.model_dump())
    return options


@router.get("/api/job/{playlist_id}")
def job_info(playlist_id: SpotifyId, request: Request, session: CurrentSession) -> JobView | None:
    """Return this playlist's job, or the last finished analysis when Spotify still agrees."""
    job = session.jobs.get(playlist_id)
    if job is not None and job.sorter is not None:
        with request.app.state.queue_lock:
            position = next(
                (
                    index
                    for index, item in enumerate(request.app.state.queue_items, start=1)
                    if item.job is job and item.action == "analyze"
                ),
                None,
            )
            running = request.app.state.running is not None and request.app.state.running.job is job
        update: dict[str, Any] = {}
        if position is not None:
            update["queue_position"] = position
        elif running:
            update["queue_position"] = None
        return job.view.model_copy(update=update)
    return _stored_view(playlist_id, session)


def _stored_view(playlist_id: SpotifyId, session: Session) -> JobView | None:
    """Serve the last finished analysis, unless Spotify says the playlist changed."""
    state = store.load_analysis(playlist_id)
    if state is None:
        return None
    try:
        view = JobView.model_validate_json(state.view_json)
    except ValidationError:
        store.delete_analysis(playlist_id)
        return None
    try:
        snapshot = get_spotify_client(session.auth).playlist(playlist_id, fields="snapshot_id").get("snapshot_id")
    except Exception:  # noqa: BLE001 - any Spotify failure means no trustworthy snapshot for this visit.
        logger.warning("Could not read the snapshot for playlist %s", playlist_id)
        return None
    if not isinstance(snapshot, str):
        return None
    view = view.model_copy(
        update={
            "stale": snapshot != state.snapshot_id,
            "can_restore": False,
            "queue_position": None,
            "stored": True,
        }
    )
    with session.lock:
        # Replace any earlier stored view so every read reflects Spotify's current snapshot.
        session.jobs[playlist_id] = Job(sorter=None, view=view, user_id=session.user["id"])
    return session.jobs[playlist_id].view


@router.get("/api/queue")
def queue_overview(request: Request, _session: CurrentSession) -> list[QueueEntry]:
    """List the running and queued playlist analyses with positions and time estimates."""
    entries: list[QueueEntry] = []
    with request.app.state.queue_lock:
        running = request.app.state.running
        if running is not None and running.action == "analyze":
            entries.append(
                QueueEntry(
                    playlist_id=running.job.view.playlist_id,
                    name=running.job.view.name,
                    status="running",
                    queue_position=None,
                    completed=running.job.view.completed,
                    total=running.job.view.total,
                    eta_seconds=_eta_seconds(running.job.view),
                )
            )
        entries.extend(
            QueueEntry(
                playlist_id=item.job.view.playlist_id,
                name=item.job.view.name,
                status="queued",
                queue_position=index,
                completed=0,
                total=0,
                eta_seconds=None,
            )
            for index, item in enumerate(
                (item for item in request.app.state.queue_items if item.action == "analyze"), start=1
            )
        )
    return entries


def _enqueue_analysis(request: Request, _session: Session, job: Job, background: BackgroundTasks) -> None:
    """Persist the queue row and wake the worker through this request's background tasks."""
    now = time.time()
    store.save_job(store.JobRow(job.view.playlist_id, job.user_id, job.view.name, "queued", PRIORITY_ANALYZE, now, now))
    item = QueueItem(priority=PRIORITY_ANALYZE, created_at=now, action="analyze", job=job)
    with request.app.state.queue_lock:
        request.app.state.queue_items.append(item)
    background.add_task(_drain, request.app)


@router.post("/api/playlists/{playlist_id}/analyze", status_code=202)
def analyze(playlist_id: SpotifyId, request: Request, session: CurrentSession, background: BackgroundTasks) -> JobView:
    """Queue an analysis of an editable playlist without blocking the response."""
    with session.lock:
        job = session.jobs.get(playlist_id)
        if job is not None and job.view.status in {"analyzing", "sorting", "saving", "restoring"}:
            return job.view
        sp = get_spotify_client(session.auth)
        info = sp.playlist(playlist_id, fields="name,owner(id),collaborative")
        if info.get("owner", {}).get("id") != session.user["id"] and not info.get("collaborative"):
            raise HTTPException(403, "Choose a playlist you can edit.")
        view = JobView(playlist_id=playlist_id, name=info.get("name") or "Your playlist")
        job = Job(SpotifyPlaylistSorter(playlist_id, sp), view, user_id=session.user["id"])
        session.jobs[playlist_id] = job
        _enqueue_analysis(request, session, job, background)
        return job.view


def begin_action(
    playlist_id: SpotifyId,
    action: str,
    body: PreviewRequest,
    session: Session,
    background: BackgroundTasks,
) -> JobView:
    """Reject stale previews and start one action for this session."""
    options = body if isinstance(body, SortRequest) else None
    with session.lock:
        job = session.jobs.get(playlist_id)
        if not job or job.sorter is None or job.view.status not in {"ready", "saved", "restored"}:
            raise HTTPException(409, "Analyze the playlist before continuing.")
        if body.revision != job.view.revision:
            raise HTTPException(409, "This preview changed in another tab. Reload the page to continue.")
        sorter = job.sorter
        if action == "sort":
            if options is None or sorter.movable_count < 2:  # noqa: PLR2004
                raise HTTPException(422, "At least two movable songs are needed to arrange this playlist.")
            error = sorter.choice_error(options.first_occurrence, options.last_occurrence, options.placements)
            if error:
                raise HTTPException(422, error)
        if action == "save" and sorter.save_problem(
            job.sorted_order, [track.occurrence for track in job.view.sorted_tracks]
        ):
            raise HTTPException(409, "Review the playlist preview before saving.")
        if action == "restore" and not sorter.can_restore:
            raise HTTPException(409, "There is no previous order to restore in this session.")
        job.view = job.view.model_copy(
            update={
                "status": {"sort": "sorting", "save": "saving", "restore": "restoring"}[action],
                "can_restore": sorter.can_restore if action == "sort" else False,
                "error": None,
                "revision": secrets.token_urlsafe(16),
            }
        )
        if action == "sort" and options is not None:
            job.sorted_order = []
            job.invalidate_preview(
                options=options.options,
                first_occurrence=options.first_occurrence,
                last_occurrence=options.last_occurrence,
                placements=dict(options.placements),
            )
        background.add_task(_run_job, job, action, lambda: None)
        return job.view


@router.post("/api/job/{playlist_id}/sort", status_code=202)
def sort(playlist_id: SpotifyId, body: SortRequest, session: CurrentSession, background: BackgroundTasks) -> JobView:
    """Preview an arrangement with the selected listening profile and endpoint pins."""
    return begin_action(playlist_id, "sort", body, session, background)


@router.post("/api/job/{playlist_id}/save", status_code=202)
def save(playlist_id: SpotifyId, body: PreviewRequest, session: CurrentSession, background: BackgroundTasks) -> JobView:
    """Apply only the preview the browser has seen."""
    return begin_action(playlist_id, "save", body, session, background)


@router.post("/api/job/{playlist_id}/restore", status_code=202)
def restore(
    playlist_id: SpotifyId, body: PreviewRequest, session: CurrentSession, background: BackgroundTasks
) -> JobView:
    """Restore the order preceding the most recent verified save in this session."""
    return begin_action(playlist_id, "restore", body, session, background)


def _match_entry(sorter: SpotifyPlaylistSorter, occurrence: str) -> dict[str, Any]:
    """Find the loaded occurrence, or reject the request with a clear reason."""
    entry = next((item for item in sorter.original_items if item["occurrence"] == occurrence), None)
    if entry is None:
        raise HTTPException(404, "This song isn't in the loaded playlist.")
    if entry["id"] is None:
        raise HTTPException(422, "This item has no Spotify recording to replace.")
    return entry


@router.get("/api/job/{playlist_id}/matches/{occurrence:path}")
def match_candidates(playlist_id: SpotifyId, occurrence: str, session: CurrentSession) -> list[Candidate]:
    """Search YouTube so a listener can review or replace this song's recording."""
    job = session.jobs.get(playlist_id)
    if (
        not job
        or job.sorter is None
        or (
            job.view.status not in {"ready", "saved", "restored"}
            and not (job.view.status == "analyzing" and job.view.rematching)
        )
    ):
        if job is not None and job.view.stored:
            raise HTTPException(409, "Re-analyze the playlist to check its recordings.")
        raise HTTPException(409, "Analyze the playlist before checking recordings.")
    sorter = job.sorter
    entry = _match_entry(sorter, occurrence)
    try:
        candidates = sorter.search_recordings(entry)
    except SourceAccessError as error:
        raise HTTPException(502, str(error)) from error
    except Exception:
        logger.exception("Recording search failed for playlist %s", playlist_id)
        raise HTTPException(502, "YouTube lookup failed. Try again later.") from None
    return [Candidate.model_validate(candidate) for candidate in candidates]


@router.post("/api/job/{playlist_id}/matches/{occurrence:path}", status_code=202)
def apply_match(  # noqa: PLR0913, PLR0917 - one identity re-analysis request.
    playlist_id: SpotifyId,
    occurrence: str,
    body: MatchRequest,
    request: Request,
    session: CurrentSession,
    background: BackgroundTasks,
) -> JobView:
    """Queue a reanalysis of this song's audio from the chosen recording, ahead of other work."""
    with session.lock:
        job = session.jobs.get(playlist_id)
        # Batched rematches keep the job in the analyzing status until the last one drains,
        # so more recordings can be chosen while earlier ones re-analyze.
        if not job or (
            job.view.status not in {"ready", "saved", "restored"}
            and not (job.view.status == "analyzing" and job.view.rematching)
        ):
            if job is not None and job.view.stored:
                raise HTTPException(409, "Re-analyze the playlist to change its recordings.")
            raise HTTPException(409, "Analyze the playlist before changing recordings.")
        if job.view.status == "saved" and job.sorted_order:
            raise HTTPException(409, "Analyze the playlist again before changing recordings.")
        sorter = job.sorter
        if sorter is None:
            raise HTTPException(409, "Analyze the playlist before changing recordings.")
        _match_entry(sorter, occurrence)  # validates the occurrence before queueing.
        with request.app.state.queue_lock:
            # Each song's rematch queues independently, so a listener can fix several
            # recordings in one pass; they run serially, one at a time.
            snapshot = sorter.snapshot_id or ""
            tracks = [
                track.model_copy(update={"analysis_status": "matching", "fixed_reason": None})
                if track.occurrence == occurrence
                else track
                for track in job.view.tracks
            ]
            job.invalidate_preview(
                status="analyzing",
                tracks=tracks,
                rematching=True,
                revision=secrets.token_urlsafe(16),
                **_analysis_counts(tracks),
            )
            request.app.state.queue_items.append(
                QueueItem(
                    priority=PRIORITY_REMATCH,
                    created_at=time.time(),
                    action="rematch",
                    job=job,
                    occurrence=occurrence,
                    video_id=body.video_id,
                    snapshot_id=snapshot,
                )
            )
        background.add_task(_drain, request.app)
        return job.view


def _run_rematch(job: Job, occurrence: str, video_id: str, snapshot_id: str) -> None:
    """Run the single-recording reanalysis through the analysis queue."""
    deadline = perf_counter() + REANALYZE_SECONDS
    try:
        # Stage deadlines inside the rematch (expired() checks and source timeouts) bound the wait.
        _rematch_job(job, occurrence, video_id, deadline, snapshot_id)
    except Exception:
        logger.exception("Playlist %s failed during rematch", job.view.playlist_id)
        tracks = [
            track.model_copy(update={"analysis_status": "error", "fixed_reason": "Couldn't update this recording"})
            if track.occurrence == occurrence
            else track
            for track in job.view.tracks
        ]
        job.view = job.view.model_copy(
            update={"tracks": tracks, "status": "ready", "error": None, **_analysis_counts(tracks)}
        )


@router.api_route("/api", include_in_schema=False, methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@router.api_route(
    "/api/{path:path}", include_in_schema=False, methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
)
def unknown_api() -> None:
    """Keep unknown API paths out of the SPA fallback."""
    raise HTTPException(404, "This page wasn't found.")


def create_app(frontend_dir: Path | None = None) -> FastAPI:
    """Create the API; a Node build supplies the static frontend directory."""
    load_dotenv()
    app = FastAPI(title="Playlist Sorter", lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.middleware("http")(private_responses)
    app.add_exception_handler(RequestValidationError, invalid_request)
    app.add_exception_handler(spotipy.SpotifyException, spotify_error)
    app.add_exception_handler(SpotifyOauthError, spotify_error)
    app.add_exception_handler(Exception, unexpected_error)
    app.include_router(router)
    app.frontend(
        "/", directory=frontend_dir or Path(__file__).resolve().parent.parent / "frontend/dist", check_dir=False
    )
    return app


app = create_app()
