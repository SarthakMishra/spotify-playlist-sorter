"""SQLite store contracts: durable sessions, shared analysis records and saved flow choices."""

# ruff: noqa: INP001, SLF001, S105

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from typing import override
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from spotipy.exceptions import SpotifyOauthError

from api import playlist_sorter, store
from api.app import COOKIE, Session, create_app
from api.audio_analysis import ANALYSIS_VERSION

DB = "store.db"
LATER = 4 * 10**12
SOON = 1000.0


class StoreTest(unittest.TestCase):
    """Verify each stored collection round-trips and cleans up after itself."""

    @override
    def setUp(self) -> None:
        """Give every test its own database file."""
        store.configure(Path(self.enterContext(tempfile.TemporaryDirectory())) / DB)

    @override
    def tearDown(self) -> None:
        store.close()

    def test_sessions_survive_a_server_reload(self) -> None:
        """A logged-in session keeps working after the server process is replaced."""
        sp = Mock()
        sp.current_user.return_value = {"id": "listener", "display_name": "A listener"}
        oauth = Mock()
        oauth.get_authorize_url.side_effect = lambda *, state: f"https://accounts.spotify.com/authorize?state={state}"
        with (
            patch.dict(os.environ, {"SPOTIFY_CLIENT_ID": "test-client", "SPOTIFY_CLIENT_SECRET": "test-secret"}),
            patch("api.app.get_redirect_uri", return_value="http://127.0.0.1:5178/api/auth/callback"),
            patch("api.app.get_auth_manager", return_value=oauth),
            patch("api.app.get_spotify_client", return_value=sp),
            TestClient(create_app()) as client,
        ):
            login = client.get("/api/auth/login", follow_redirects=False)
            state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
            callback = client.get(f"/api/auth/callback?code=test&state={state}", follow_redirects=False)
            assert callback.status_code == 303
            cookie = client.cookies.get(COOKIE)
        assert cookie is not None

        with TestClient(create_app()) as client, patch("api.app.get_spotify_client", return_value=sp):
            client.cookies.set(COOKIE, cookie)
            session = client.get("/api/session").json()
            assert session["user"] == {"id": "listener", "name": "A listener"}
            assert client.get(f"/api/job/{'p' * 22}").json() is None

        store.delete_expired(LATER)
        with TestClient(create_app()) as client:
            client.cookies.set(COOKIE, cookie)
            assert client.get("/api/session").json()["user"] is None

    def test_queued_analyses_reenqueue_after_a_server_reload(self) -> None:
        """Queued or interrupted analyses are rebuilt with the owner's session after a reload."""
        sp = Mock()
        sp.current_user.return_value = {"id": "listener", "display_name": "A listener"}
        sp.playlist.return_value = {"name": "Evening", "snapshot_id": "snapshot", "owner": {"id": "listener"}}
        sp.playlist_items.return_value = {
            "items": [{"item": {"id": "a", "name": "One", "artists": [], "type": "track"}}],
            "next": None,
        }
        oauth = Mock()
        oauth.get_authorize_url.side_effect = lambda *, state: f"https://accounts.spotify.com/authorize?state={state}"
        with (
            patch.dict(os.environ, {"SPOTIFY_CLIENT_ID": "test-client", "SPOTIFY_CLIENT_SECRET": "test-secret"}),
            patch("api.app.get_redirect_uri", return_value="http://127.0.0.1:5178/api/auth/callback"),
            patch("api.app.get_auth_manager", return_value=oauth),
            patch("api.app.get_spotify_client", return_value=sp),
            TestClient(create_app()) as client,
        ):
            login = client.get("/api/auth/login", follow_redirects=False)
            state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
            client.get(f"/api/auth/callback?code=test&state={state}", follow_redirects=False)
            cookie = client.cookies.get(COOKIE)
        assert cookie is not None

        now = time.time()
        store.save_job(store.JobRow("p" * 22, "listener", "Evening", "queued", 10, now, now))
        store.save_job(store.JobRow("q" * 22, "listener", "Orphan", "running", 10, now, now))
        job = None
        features = {key: {"status": "ready", "tempo": 120.0, "camelot": None, "energy": 0.5} for key in ("a", "b")}
        with (
            patch("api.app.get_spotify_client", return_value=sp),
            patch.object(playlist_sorter.SpotifyPlaylistSorter, "_fetch_audio_features_local", return_value=features),
            TestClient(create_app()) as client,
        ):
            client.cookies.set(COOKIE, cookie)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                job = client.get("/api/job/" + "p" * 22).json()
                if job and job["status"] in {"ready", "error"}:
                    break
                time.sleep(0.05)
            assert job is not None
            assert job["status"] == "ready"
            # The orphaned row lost its owner's session is dropped instead of analyzed.
            assert store.load_job("q" * 22, "listener") is None

    def test_refreshed_tokens_are_persisted(self) -> None:
        """A token refresh during a request updates the stored session row."""
        with patch.dict(os.environ, {"SPOTIFY_CLIENT_ID": "test-client", "SPOTIFY_CLIENT_SECRET": "test-secret"}):
            app = create_app()
        token = json.dumps({"access_token": "old", "expires_at": 1000})
        store.save_session(store.SessionRow("test-session", "", "csrf", "listener", "A listener", token, 1000.0, LATER))
        with TestClient(app) as client:
            client.cookies.set(COOKIE, "test-session")
            assert client.get("/api/preferences").status_code == 200
            refreshed = {
                "access_token": "new-access",
                "refresh_token": "same-refresh",
                "expires_at": LATER,
            }
            app.state.sessions["test-session"].auth.cache_handler.save_token_to_cache(refreshed)
            assert client.get("/api/preferences").status_code == 200
        row = store.load_session("test-session")
        assert row is not None
        token = json.loads(row.token_json)
        assert token["access_token"] == "new-access"
        assert row.token_expires == float(LATER)

    def test_revoked_tokens_are_forgotten(self) -> None:
        """A 401 from Spotify removes the stored session so reloads cannot revive it."""
        sp = Mock()
        sp.current_user_playlists.side_effect = SpotifyOauthError("invalid_grant", "Token expired")
        store.save_session(store.SessionRow("test-session", "", "csrf", "listener", "A listener", "", 0.0, LATER))
        with TestClient(create_app()) as client, patch("api.app.get_spotify_client", return_value=sp):
            client.cookies.set(COOKIE, "test-session")
            assert client.get("/api/playlists").status_code == 401
        assert store.load_session("test-session") is None

    def test_sessions_cannot_exceed_the_cap(self) -> None:
        """Admission is decided by the durable count, including sessions of other processes."""
        for index in range(200):
            store.save_session(store.SessionRow(f"s{index}", "", "csrf", "u", "n", "", 0.0, LATER))
        with (
            patch.dict(os.environ, {"SPOTIFY_CLIENT_ID": "test-client", "SPOTIFY_CLIENT_SECRET": "test-secret"}),
            patch("api.app.get_redirect_uri", return_value="http://127.0.0.1:5178/api/auth/callback"),
            TestClient(create_app()) as client,
        ):
            assert client.get("/api/auth/login", follow_redirects=False).status_code == 503

    def test_analysis_cache_versions_and_stale_files(self) -> None:
        """Records load from SQLite only, and analysis version changes reset every record."""
        assert playlist_sorter._load_cache() == {}
        store.save_cache_records({"t1": json.dumps({"status": "ready", "source": {"id": "abcdefghijk"}})})
        assert playlist_sorter._load_cache() == {"t1": {"status": "ready", "source": {"id": "abcdefghijk"}}}

        store.reset_cache({"analysis_version": "old-version"}, {})
        assert playlist_sorter._load_cache() == {}
        stored = store.cache_meta()
        assert stored is not None
        assert stored["analysis_version"] == str(ANALYSIS_VERSION)

    def test_preferences_round_trip(self) -> None:
        """Saved flow choices come back exactly and survive a re-save."""
        assert store.get_preferences("listener") is None
        store.save_preferences("listener", {"preset": "buildup", "pace": 0.4, "energy": 0.8, "variety": 0.2})
        assert store.get_preferences("listener") == {
            "preset": "buildup",
            "pace": 0.4,
            "energy": 0.8,
            "variety": 0.2,
        }
        store.save_preferences("listener", {"preset": "mixed", "pace": 0.5, "energy": 0.5, "variety": 0.9})
        saved = store.get_preferences("listener")
        assert saved is not None
        assert saved["preset"] == "mixed"

    def test_preferences_endpoints(self) -> None:
        """The HTTP contract validates choices and returns defaults before a save."""
        app = create_app()
        with TestClient(app) as client:
            app.state.sessions["test-session"] = Session(auth=Mock(), state="", user={"id": "listener"})
            client.cookies.set(COOKIE, "test-session")
            assert client.get("/api/preferences").json() == {
                "preset": "steady",
                "pace": 0.5,
                "energy": 0.5,
                "variety": 0.5,
            }
            headers = {"X-CSRF-Token": client.get("/api/session").json()["csrf"]}
            assert (
                client.put(
                    "/api/preferences",
                    headers=headers,
                    json={"preset": "gentle", "pace": 0.2, "energy": 0.3, "variety": 0.1},
                ).status_code
                == 200
            )
            assert client.get("/api/preferences").json()["preset"] == "gentle"
            assert (
                client.put("/api/preferences", headers=headers, json={"preset": "gentle", "pace": 5}).status_code == 422
            )

    def test_wipe_clears_every_table(self) -> None:
        """A wiped database starts empty without losing its schema."""
        store.save_session(store.SessionRow("s", "", "c", "u", "n", "", 0.0, LATER))
        store.wipe()
        assert store.load_session("s") is None
        assert store.get_preferences("listener") is None
        assert store.count_sessions() == 0
