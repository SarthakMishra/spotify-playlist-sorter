"""FastAPI endpoints and the compiled React app."""

from __future__ import annotations

import json
import logging
import secrets
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Annotated, Any, Literal, cast
from urllib.parse import urlsplit

import pandas as pd
import spotipy
from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from spotipy.exceptions import SpotifyOauthError

from api.playlist_sorter import Profile, SpotifyPlaylistSorter
from api.spotify_auth import get_all_playlists, get_auth_manager, get_redirect_uri, get_spotify_client, is_configured

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from spotipy.oauth2 import SpotifyOAuth

logger = logging.getLogger(__name__)
SESSION_SECONDS = 24 * 60 * 60
LOGIN_SECONDS = 10 * 60
MAX_SESSIONS = 200
COOKIE = "playlist_session"
SpotifyId = Annotated[str, Field(pattern=r"^[A-Za-z0-9]{22}$")]


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
    cached_count: int = 0
    recording_count: int = 0
    metadata_loaded: bool = False
    analyzed_count: int = 0
    profile: Profile = "smooth"
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

    sorter: SpotifyPlaylistSorter
    view: JobView
    sorted_order: list[str] = field(default_factory=list)


@dataclass
class Session:
    """Server-only OAuth state with an opaque browser cookie."""

    auth: SpotifyOAuth
    state: str
    expires: float = field(default_factory=lambda: time.time() + LOGIN_SECONDS)
    csrf: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    user: dict[str, str] = field(default_factory=dict)
    job: Job | None = None
    lock: Lock = field(default_factory=Lock)


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
    """Select a listening profile, optional endpoint pins and unanalyzable-item placements."""

    profile: Profile = "smooth"
    first_occurrence: Annotated[str, Field(min_length=1, max_length=512)] | None = None
    last_occurrence: Annotated[str, Field(min_length=1, max_length=512)] | None = None
    placements: dict[Annotated[str, Field(min_length=1, max_length=512)], Annotated[int, Field(ge=0)]] = Field(
        default_factory=dict
    )


def _lookup_session(request: Request) -> Session | None:
    with request.app.state.sessions_lock:
        sessions = cast("dict[str, Session]", request.app.state.sessions)
        for key in list(sessions):
            if sessions[key].expires < time.time():
                del sessions[key]
        return sessions.get(request.cookies.get(COOKIE))


def _require_session(request: Request) -> Session:
    session = _lookup_session(request)
    if session is None or not session.user:
        raise HTTPException(401, "Connect Spotify to continue.")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("X-CSRF-Token", "")
        if not secrets.compare_digest(csrf, session.csrf):
            raise HTTPException(403, "Refresh the page and try again.")
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


def _tracks(frame: pd.DataFrame) -> list[Track]:
    """Serialize the entry identities assigned when the source playlist was loaded."""
    columns = {"Track": "name", "Artist": "artist", "Camelot": "key", "BPM": "bpm", "Energy": "energy"}
    return [
        Track.model_validate(row) for row in json.loads(frame.rename(columns=columns).to_json(orient="records") or "[]")
    ]


def _analysis_counts(tracks: list[Track]) -> dict[str, int]:
    """Count completed measurements separately from entries that must stay in place."""
    return {
        "analyzed_count": sum(track.analysis_status == "ready" for track in tracks),
        "kept_count": sum(track.fixed_reason is not None for track in tracks),
    }


def _analyze_job(job: Job) -> None:
    """Publish complete metadata and serialize parallel recording progress."""
    progress_lock = Lock()

    def entries_loaded(entries: list[dict[str, Any]]) -> None:
        tracks = _tracks(pd.DataFrame(entries))
        with progress_lock:
            job.view = job.view.model_copy(
                update={
                    "metadata_loaded": True,
                    "tracks": tracks,
                    "name": job.sorter.playlist_name or "Your playlist",
                    "total": sum(track.analysis_status == "pending" for track in tracks),
                    **_analysis_counts(tracks),
                }
            )

    def record_progress(recording_id: str, result: dict[str, Any]) -> None:
        phase = "fixed" if result["status"] == "unsupported" else result["status"]
        reason = (
            result.get("message", "Couldn't analyze this song") if phase in {"fixed", "uncertain", "error"} else None
        )
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
                update={
                    "completed": done,
                    "total": total,
                    "cached_count": job.sorter.cached_count,
                    "recording_count": job.sorter.recording_count,
                }
            )

    tracks = job.sorter.load_playlist(
        progress_callback=progress, entries_callback=entries_loaded, record_callback=record_progress
    )
    if tracks is None:
        job.view = job.view.model_copy(
            update={"status": "error", "error": "We couldn't analyze these songs. Please try again."}
        )
        return
    job.view = job.view.model_copy(
        update={
            "name": job.sorter.playlist_name or "Your playlist",
            "tracks": _tracks(tracks),
            "metadata_loaded": True,
            "completed": job.view.total,
            "analyzed_count": sum(entry["analysis_status"] == "ready" for entry in job.sorter.original_items),
            "kept_count": sum(entry["fixed_reason"] is not None for entry in job.sorter.original_items),
            "cached_count": job.sorter.cached_count,
            "recording_count": job.sorter.recording_count,
            "status": "ready",
        }
    )


def _run_job(job: Job, action: str, release: Callable[[], None]) -> None:
    """Run blocking work in FastAPI's background thread pool."""
    try:
        if action == "analyze":
            _analyze_job(job)
        elif action == "sort":
            job.sorted_order = job.sorter.sort_playlist(
                job.view.first_occurrence, job.view.last_occurrence, job.view.profile, job.view.placements
            )
            if not job.sorted_order:
                job.view = job.view.model_copy(
                    update={"status": "error", "error": "Review your song choices and try again."}
                )
                return
            _, sorted_frame = job.sorter.compare_playlists(job.sorted_order)
            transitions = job.sorter.get_transition_analysis(job.sorted_order)
            job.view = job.view.model_copy(
                update={
                    "sorted_tracks": _tracks(sorted_frame),
                    "transitions": json.loads(pd.DataFrame(transitions).to_json(orient="records") or "[]"),
                    "review": job.sorter.review_summary(job.sorted_order, transitions),
                    "arrangement": {
                        key: value
                        for key, value in job.sorter.arrangement_result.items()
                        if key not in {"order", "profile", "first_occurrence", "last_occurrence", "placements"}
                    },
                    "status": "ready",
                }
            )
        elif action == "restore":
            success, message = job.sorter.restore_spotify_playlist()
            job.sorted_order = job.sorter.current_order.copy() if success else []
            _, restored_frame = job.sorter.compare_playlists(job.sorted_order)
            job.view = job.view.model_copy(
                update={
                    "status": "restored" if success else "error",
                    "error": None if success else message,
                    "can_restore": False,
                    "sorted_tracks": _tracks(restored_frame),
                    "transitions": [],
                    "review": None,
                    "arrangement": None,
                    "first_occurrence": None,
                    "last_occurrence": None,
                    "placements": {},
                }
            )
        else:
            success, message = job.sorter.update_spotify_playlist(job.sorted_order)
            job.view = job.view.model_copy(
                update={
                    "status": "saved" if success else "error",
                    "error": None if success else message,
                    "can_restore": job.sorter.can_restore,
                }
            )
    except Exception:
        logger.exception("Playlist %s failed during %s", job.view.playlist_id, action)
        message = "Something went wrong. Please analyze the playlist again."
        if action in {"save", "restore"}:
            job.sorter.invalidate_save()
            job.view = job.view.model_copy(update={"can_restore": False})
            message = "The change couldn't be verified. Some songs may have moved. Analyze the playlist again."
        if action == "analyze":
            tracks = [
                track.model_copy(update={"analysis_status": "error", "fixed_reason": "Analysis interrupted"})
                if track.analysis_status in {"pending", "matching", "downloading", "analyzing"}
                else track
                for track in job.view.tracks
            ]
            job.view = job.view.model_copy(update={"tracks": tracks, **_analysis_counts(tracks)})
        job.view = job.view.model_copy(update={"status": "error", "error": message})
    finally:
        release()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Keep session state within this server process."""
    app.state.sessions = {}
    app.state.sessions_lock = Lock()
    # ponytail: one playlist analysis at a time; add a durable queue before running multiple server workers.
    app.state.analysis_lock = Lock()
    yield
    app.state.sessions.clear()


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
    state = secrets.token_urlsafe(32)
    session = Session(auth=get_auth_manager(state), state=state)
    session_id = secrets.token_urlsafe(32)
    with request.app.state.sessions_lock:
        if len(request.app.state.sessions) >= MAX_SESSIONS:
            raise HTTPException(503, "We're busy right now. Please try again soon.")
        old_id = request.cookies.get(COOKIE)
        request.app.state.sessions.pop(old_id, None)
        request.app.state.sessions[session_id] = session
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
        with request.app.state.sessions_lock:
            request.app.state.sessions.pop(request.cookies.get(COOKIE), None)
            request.app.state.sessions[session_id] = session
    response = RedirectResponse("/playlists", status_code=303)
    _set_cookie(response, session_id)
    return response


@router.post("/api/auth/logout")
def logout(request: Request, response: Response, _session: CurrentSession) -> dict[str, bool]:
    """Forget this browser session and expire its cookie."""
    with request.app.state.sessions_lock:
        request.app.state.sessions.pop(request.cookies.get(COOKIE), None)
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.get("/api/playlists")
def playlists(session: CurrentSession) -> list[Playlist]:
    """List the playlists this listener can edit."""
    return [Playlist.model_validate(p) for p in get_all_playlists(get_spotify_client(session.auth), session.user["id"])]


@router.get("/api/job")
def job_info(session: CurrentSession) -> JobView | None:
    """Return this session's current playlist and progress."""
    return session.job.view if session.job else None


@router.post("/api/playlists/{playlist_id}/analyze", status_code=202)
def analyze(playlist_id: SpotifyId, request: Request, session: CurrentSession, background: BackgroundTasks) -> JobView:
    """Analyze an editable playlist without blocking the response."""
    with session.lock:
        if session.job and session.job.view.status in {"analyzing", "sorting", "saving", "restoring"}:
            raise HTTPException(409, "Please wait for this playlist to finish.")
        if not request.app.state.analysis_lock.acquire(blocking=False):
            raise HTTPException(409, "We're analyzing another playlist. Please try again shortly.")
        try:
            sp = get_spotify_client(session.auth)
            info = sp.playlist(playlist_id, fields="owner(id),collaborative")
            if info.get("owner", {}).get("id") != session.user["id"] and not info.get("collaborative"):
                raise HTTPException(403, "Choose a playlist you can edit.")  # noqa: TRY301
            job = Job(SpotifyPlaylistSorter(playlist_id, sp), JobView(playlist_id=playlist_id))
            session.job = job
            background.add_task(_run_job, job, "analyze", request.app.state.analysis_lock.release)
        except Exception:
            request.app.state.analysis_lock.release()
            raise
        else:
            return job.view


def begin_action(
    session: Session, background: BackgroundTasks, action: str, revision: str, options: SortRequest | None = None
) -> JobView:
    """Reject stale previews and start one action for this session."""
    with session.lock:
        job = session.job
        if not job or job.view.status not in {"ready", "saved", "restored"}:
            raise HTTPException(409, "Analyze the playlist before continuing.")
        if revision != job.view.revision:
            raise HTTPException(409, "This preview changed in another tab. Reload the page to continue.")
        if action == "sort":
            movable = {track.occurrence for track in job.view.tracks if track.fixed_reason is None}
            if options is None or len(movable) < 2:  # noqa: PLR2004
                raise HTTPException(422, "At least two movable songs are needed to arrange this playlist.")
            error = job.sorter.choice_error(
                options.first_occurrence, options.last_occurrence, options.profile, options.placements
            )
            if error:
                raise HTTPException(422, error)
        if action == "save" and (
            not job.sorter.valid_order(job.sorted_order)
            or job.sorted_order != [track.occurrence for track in job.view.sorted_tracks]
            or job.sorted_order == job.sorter.current_order
        ):
            raise HTTPException(409, "Review the playlist preview before saving.")
        if action == "restore" and not job.sorter.can_restore:
            raise HTTPException(409, "There is no previous order to restore in this session.")
        job.view = job.view.model_copy(
            update={
                "status": {"sort": "sorting", "save": "saving", "restore": "restoring"}[action],
                "can_restore": job.sorter.can_restore if action == "sort" else False,
                "error": None,
                "revision": secrets.token_urlsafe(16),
            }
        )
        if action == "sort" and options is not None:
            job.sorted_order = []
            job.view = job.view.model_copy(
                update={
                    **options.model_dump(exclude={"revision"}),
                    "sorted_tracks": [],
                    "transitions": [],
                    "arrangement": None,
                    "review": None,
                }
            )
        background.add_task(_run_job, job, action, lambda: None)
        return job.view


@router.post("/api/job/sort", status_code=202)
def sort(body: SortRequest, session: CurrentSession, background: BackgroundTasks) -> JobView:
    """Preview an arrangement with the selected listening profile and endpoint pins."""
    return begin_action(session, background, "sort", body.revision, body)


@router.post("/api/job/save", status_code=202)
def save(body: PreviewRequest, session: CurrentSession, background: BackgroundTasks) -> JobView:
    """Apply only the preview the browser has seen."""
    return begin_action(session, background, "save", body.revision)


@router.post("/api/job/restore", status_code=202)
def restore(body: PreviewRequest, session: CurrentSession, background: BackgroundTasks) -> JobView:
    """Restore the order preceding the most recent verified save in this session."""
    return begin_action(session, background, "restore", body.revision)


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
