"""Offline browser flow and Spotify reorder regression checks."""

# ruff: noqa: INP001

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from spotipy.exceptions import SpotifyOauthError

from app.app import COOKIE, Session, create_app
from app.playlist_sorter import SpotifyPlaylistSorter

PLAYLIST = "p" * 22
FIRST = "a" * 22
SECOND = "b" * 22
UNCHECKED = "c" * 22


def spotify_item(track_id: str, name: str) -> dict[str, Any]:
    """Use Spotify's 2026 item response shape."""
    return {"item": {"id": track_id, "name": name, "artists": [{"name": "An artist"}], "type": "track"}}


class MigrationTest(unittest.TestCase):
    """Exercise HTTP contracts and the real sorting code with external I/O mocked."""

    def test_browser_flow_and_safe_reordering(self) -> None:  # noqa: PLR0915
        """Preview stays private and saving keeps duplicate, failed, and unavailable songs."""
        sp = Mock()
        sp.current_user.return_value = {"id": "listener", "display_name": "A listener"}
        sp.playlist.return_value = {"name": "Evening", "snapshot_id": "snapshot", "owner": {"id": "listener"}}
        sp.current_user_playlists.return_value = {
            "items": [
                {"id": PLAYLIST, "name": "Evening", "items": {"total": 5}, "owner": {"id": "listener"}},
                {"id": "q" * 22, "name": "Evening", "tracks": {"total": 1}, "collaborative": True},
                {"id": "r" * 22, "name": "Not editable", "owner": {"id": "someone-else"}},
            ],
            "next": None,
        }
        original = [FIRST, UNCHECKED, SECOND, None, FIRST]
        current = original.copy()
        sp.playlist_items.return_value = {
            "items": [
                spotify_item(FIRST, "First"),
                spotify_item(UNCHECKED, "Unknown"),
                spotify_item(SECOND, "Second"),
                {"item": None},
                spotify_item(FIRST, "First"),
            ],
            "next": None,
        }

        def reorder(_playlist: str, source: int, destination: int, **kwargs: object) -> dict[str, Any]:
            assert kwargs["snapshot_id"] == "snapshot"
            current.insert(destination, current.pop(source))
            return {"snapshot_id": "snapshot"}

        sp.playlist_reorder_items.side_effect = reorder
        features = {
            FIRST: {"tempo": 120.0, "energy": 0.5, "camelot": "8B", "key": 0},
            SECOND: {"tempo": 122.0, "energy": 0.7, "camelot": "9B", "key": 7},
        }
        oauth = Mock()
        oauth.get_authorize_url.side_effect = lambda *, state: f"https://accounts.spotify.com/authorize?state={state}"
        with (
            tempfile.TemporaryDirectory() as temp,
            patch("app.app.is_configured", return_value=True),
            patch("app.app.get_redirect_uri", return_value="http://127.0.0.1:8000/api/auth/callback"),
            patch("app.app.get_auth_manager", return_value=oauth),
            patch("app.app.get_spotify_client", return_value=sp),
            patch.object(SpotifyPlaylistSorter, "_fetch_audio_features_local", return_value=features),
        ):
            directory = Path(temp)
            (directory / "index.html").write_text("<html>Playlist sorter</html>")
            (directory / "assets").mkdir()
            (directory / "assets/app.js").write_text("console.log('app')")
            app = create_app(directory)
            with TestClient(app) as client:
                assert client.get("/api/playlists").status_code == 401
                assert client.get("/api/session").json()["user"] is None
                login = client.get("/api/auth/login", follow_redirects=False)
                state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
                assert "httponly" in login.headers["set-cookie"].lower()
                assert "samesite=lax" in login.headers["set-cookie"].lower()
                old_cookie = client.cookies.get(COOKIE)
                bad = client.get("/api/auth/callback?code=test&state=wrong", follow_redirects=False)
                assert bad.headers["location"] == "/?error=login"
                oauth.get_access_token.assert_not_called()
                callback = client.get(f"/api/auth/callback?code=test&state={state}", follow_redirects=False)
                assert callback.headers["location"] == "/playlists"
                assert old_cookie != client.cookies.get(COOKIE)
                client.get(f"/api/auth/callback?code=test&state={state}", follow_redirects=False)
                oauth.get_access_token.assert_called_once()
                session_response = client.get("/api/session")
                assert session_response.headers["cache-control"] == "no-store"
                session = session_response.json()
                assert set(session) == {"configured", "user", "csrf"}
                headers = {"X-CSRF-Token": session["csrf"]}
                playlists = client.get("/api/playlists").json()
                assert len(playlists) == 2
                assert playlists[0]["total"] == 5
                assert client.post(f"/api/playlists/{PLAYLIST}/analyze").status_code == 403
                assert client.post("/api/playlists/invalid/analyze", headers=headers).status_code == 422
                app.state.analysis_lock.acquire()
                assert client.post(f"/api/playlists/{PLAYLIST}/analyze", headers=headers).status_code == 409
                app.state.analysis_lock.release()
                assert client.post(f"/api/playlists/{PLAYLIST}/analyze", headers=headers).status_code == 202
                job = client.get("/api/job").json()
                assert job["status"] == "ready"
                assert job["kept_count"] == 2
                assert len(job["tracks"]) == 3
                sp.playlist_reorder_items.assert_not_called()
                assert (
                    client.post(
                        "/api/job/sort",
                        headers=headers,
                        json={"revision": job["revision"], "first_track_id": UNCHECKED},
                    ).status_code
                    == 422
                )
                assert (
                    client.post("/api/job/save", headers=headers, json={"revision": job["revision"]}).status_code == 409
                )
                assert (
                    client.post(
                        "/api/job/sort", headers=headers, json={"revision": job["revision"], "first_track_id": SECOND}
                    ).status_code
                    == 202
                )
                preview = client.get("/api/job").json()
                assert [track["id"] for track in preview["sorted_tracks"]] == [SECOND, FIRST, FIRST]
                assert len(preview["transitions"]) == 2
                sp.playlist_reorder_items.assert_not_called()
                assert (
                    client.post("/api/job/save", headers=headers, json={"revision": job["revision"]}).status_code == 409
                )
                # Another browser cannot read or save this browser's job.
                other = TestClient(app)
                assert other.get("/api/job").status_code == 401
                assert (
                    other.post("/api/job/save", headers=headers, json={"revision": preview["revision"]}).status_code
                    == 401
                )
                other.close()
                assert (
                    client.post("/api/job/save", headers=headers, json={"revision": preview["revision"]}).status_code
                    == 202
                )
                assert client.get("/api/job").json()["status"] == "saved"
                assert current == [SECOND, UNCHECKED, FIRST, None, FIRST]
                sp.playlist_replace_items.assert_not_called()
                sp.playlist_add_items.assert_not_called()
                assert (
                    client.get(f"/playlists/{PLAYLIST}", headers={"Accept": "text/html"}).text
                    == "<html>Playlist sorter</html>"
                )
                assert client.get("/assets/app.js").status_code == 200
                assert client.get("/assets/missing.js").status_code == 404
                assert client.get("/api/missing", headers={"Accept": "text/html"}).status_code == 404
                assert client.get("/api", headers={"Accept": "text/html"}).status_code == 404
                assert client.get("/api/missing").headers["content-type"] == "application/json"
                assert client.post("/api/auth/logout", headers=headers).status_code == 200
                assert client.cookies.get(COOKIE) is None
                assert client.get("/api/job").status_code == 401

    def test_changed_or_failed_saves_never_replace_songs(self) -> None:
        """Reject stale snapshots and report partial reorders without deleting items."""
        sp = Mock()
        sorter = SpotifyPlaylistSorter(PLAYLIST, sp)
        sorter.original_items = [FIRST, UNCHECKED, SECOND, None, FIRST]
        sorter.original_track_order = [FIRST, SECOND, FIRST]
        sorter.snapshot_id = "before"
        sp.playlist.return_value = {"snapshot_id": "changed"}
        success, message = sorter.update_spotify_playlist([SECOND, FIRST, FIRST])
        assert not success
        assert "changed on Spotify" in message
        sp.playlist_reorder_items.assert_not_called()
        sp.playlist.return_value = {"snapshot_id": "before"}
        sp.playlist_reorder_items.side_effect = [{"snapshot_id": "after-one-move"}, RuntimeError("Connection lost")]
        success, message = sorter.update_spotify_playlist([SECOND, FIRST, FIRST])
        assert not success
        assert "Some songs may have moved" in message
        assert sorter.snapshot_id is None
        sp.playlist_replace_items.assert_not_called()
        sp.playlist_add_items.assert_not_called()
        count = sp.playlist_reorder_items.call_count
        assert not sorter.update_spotify_playlist([SECOND, FIRST, FIRST])[0]
        assert sp.playlist_reorder_items.call_count == count
        assert not sorter.update_spotify_playlist([SECOND, FIRST])[0]

    def test_revoked_login_clears_the_browser_session(self) -> None:
        """A revoked refresh token must not leave the browser stuck in a login loop."""
        app = create_app()
        sp = Mock()
        sp.current_user_playlists.side_effect = SpotifyOauthError("invalid_grant", "Token expired")
        with TestClient(app) as client, patch("app.app.get_spotify_client", return_value=sp):
            app.state.sessions["test-session"] = Session(auth=Mock(), state="", user={"id": "listener"})
            client.cookies.set(COOKIE, "test-session")
            assert client.get("/api/playlists").status_code == 401
            assert client.get("/api/session").json()["user"] is None
            assert client.get("/api/job").status_code == 401

    def test_localhost_login_sets_the_cookie_on_the_callback_host(self) -> None:
        """Normalize the hostname before OAuth so the callback receives its session cookie."""
        for port in (8000, 5173):
            callback = f"http://127.0.0.1:{port}/api/auth/callback"
            with (
                self.subTest(port=port),
                patch.dict(
                    os.environ,
                    {
                        "SPOTIFY_CLIENT_ID": "test-client",
                        "SPOTIFY_CLIENT_SECRET": "test-secret",
                        "SPOTIFY_REDIRECT_URI": callback,
                    },
                ),
            ):
                app = create_app()
                with TestClient(app, base_url=f"http://localhost:{port}") as client:
                    first = client.get("/api/auth/login", follow_redirects=False)
                    expected = f"http://127.0.0.1:{port}/api/auth/login"
                    assert first.headers["location"] == expected
                    assert "set-cookie" not in first.headers
                    second = client.get(expected, follow_redirects=False)
                    query = parse_qs(urlparse(second.headers["location"]).query)
                    assert query["redirect_uri"] == [callback]
                    assert "set-cookie" in second.headers
                    sp = Mock()
                    sp.current_user.return_value = {"id": "listener"}
                    with patch("app.app.get_spotify_client", return_value=sp):
                        session = next(iter(app.state.sessions.values()))
                        session.auth.get_access_token = Mock(return_value="test-token")
                        response = client.get(
                            callback, params={"code": "test", "state": query["state"][0]}, follow_redirects=False
                        )
                    assert response.headers["location"] == "/playlists"
