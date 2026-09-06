"""Offline browser flow and Spotify reorder regression checks."""

# ruff: noqa: INP001

from __future__ import annotations

import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from itertools import pairwise
from pathlib import Path
from threading import Event
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from spotipy.exceptions import SpotifyOauthError

from api.app import COOKIE, Session, create_app
from api.playlist_sorter import SpotifyPlaylistSorter

if TYPE_CHECKING:
    from collections.abc import Callable

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
        current_positions = list(range(len(original)))
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

        original_items = sp.playlist_items.return_value["items"]
        sp.playlist_items.side_effect = lambda *_: {
            "items": [original_items[index] for index in current_positions],
            "next": None,
        }

        def reorder(_playlist: str, source: int, destination: int, **kwargs: object) -> dict[str, Any]:
            assert kwargs["snapshot_id"] == "snapshot"
            current.insert(destination, current.pop(source))
            current_positions.insert(destination, current_positions.pop(source))
            return {"snapshot_id": "snapshot"}

        sp.playlist_reorder_items.side_effect = reorder
        features: dict[str, dict[str, Any]] = {
            FIRST: {"status": "ready", "tempo": 120.0, "energy": 0.5, "camelot": "8B", "key": 0},
            SECOND: {"status": "ready", "tempo": 122.0, "energy": 0.7, "camelot": "9B", "key": 7},
        }
        oauth = Mock()
        oauth.get_authorize_url.side_effect = lambda *, state: f"https://accounts.spotify.com/authorize?state={state}"
        with (
            tempfile.TemporaryDirectory() as temp,
            patch("api.app.is_configured", return_value=True),
            patch("api.app.get_redirect_uri", return_value="http://127.0.0.1:5178/api/auth/callback"),
            patch("api.app.get_auth_manager", return_value=oauth),
            patch("api.app.get_spotify_client", return_value=sp),
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
                assert job["completed"] == job["total"]
                assert job["kept_count"] == 2
                assert [track["id"] for track in job["tracks"]] == original
                occurrences = [track["occurrence"] for track in job["tracks"]]
                assert len(set(occurrences)) == len(original)
                assert [track["original_position"] for track in job["tracks"]] == list(range(len(original)))
                assert job["tracks"][1]["fixed_reason"] == "Couldn't analyze this song"
                assert job["tracks"][3]["name"] == "Unavailable item"
                sp.playlist_reorder_items.assert_not_called()
                assert (
                    client.post(
                        "/api/job/sort",
                        headers=headers,
                        json={"revision": job["revision"], "first_occurrence": occurrences[1]},
                    ).status_code
                    == 422
                )
                assert (
                    client.post("/api/job/save", headers=headers, json={"revision": job["revision"]}).status_code == 409
                )
                assert (
                    client.post(
                        "/api/job/sort",
                        headers=headers,
                        json={"revision": job["revision"], "first_occurrence": occurrences[2]},
                    ).status_code
                    == 202
                )
                preview = client.get("/api/job").json()
                assert [track["id"] for track in preview["sorted_tracks"]] == [SECOND, UNCHECKED, FIRST, None, FIRST]
                assert len(preview["transitions"]) == 4
                target = [occurrences[i] for i in (2, 1, 0, 3, 4)]
                assert [track["occurrence"] for track in preview["sorted_tracks"]] == target
                assert all(transition["score"] is None for transition in preview["transitions"])
                assert [(t["track1_occurrence"], t["track2_occurrence"]) for t in preview["transitions"]] == list(
                    pairwise(target)
                )
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
                assert current_positions == [2, 1, 0, 3, 4]
                # Pick the other copy of First, then save again from the current Spotify order.
                saved = client.get("/api/job").json()
                assert (
                    client.post(
                        "/api/job/sort",
                        headers=headers,
                        json={"revision": saved["revision"], "first_occurrence": occurrences[4]},
                    ).status_code
                    == 202
                )
                second_preview = client.get("/api/job").json()
                assert second_preview["sorted_tracks"][0]["occurrence"] == occurrences[4]
                assert [track["occurrence"] for track in second_preview["tracks"]] == occurrences
                assert (
                    client.post(
                        "/api/job/save",
                        headers=headers,
                        json={"revision": second_preview["revision"]},
                    ).status_code
                    == 202
                )
                assert current_positions == [4, 1, 0, 3, 2]
                assert current == [track["id"] for track in second_preview["sorted_tracks"]]
                saved = client.get("/api/job").json()
                assert saved["can_restore"]
                assert client.post("/api/job/restore", json={"revision": saved["revision"]}).status_code == 403
                assert (
                    client.post(
                        "/api/job/restore", headers=headers, json={"revision": second_preview["revision"]}
                    ).status_code
                    == 409
                )
                assert (
                    client.post("/api/job/restore", headers=headers, json={"revision": saved["revision"]}).status_code
                    == 202
                )
                restored = client.get("/api/job").json()
                assert restored["status"] == "restored"
                assert not restored["can_restore"]
                assert restored["first_occurrence"] is None
                assert current_positions == [2, 1, 0, 3, 4]
                assert [track["occurrence"] for track in restored["sorted_tracks"]] == target
                assert (
                    client.post(
                        "/api/job/restore", headers=headers, json={"revision": restored["revision"]}
                    ).status_code
                    == 409
                )
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

    def test_unchecked_and_sparse_playlists_remain_visible(self) -> None:
        """Retain all metadata and placeholders when zero or one song can move."""
        sp = Mock()
        sp.playlist.return_value = {"name": "Mixed items", "snapshot_id": "snapshot", "owner": {"id": "listener"}}
        sp.playlist_items.return_value = {
            "items": [
                None,
                {"item": None},
                {"item": {"name": "Local song", "id": None}, "is_local": True},
                {"item": {"id": "e" * 22, "name": "An episode", "type": "episode"}},
                spotify_item(UNCHECKED, "Uncertain song"),
            ],
            "next": None,
        }
        app = create_app()
        for features in ({}, {UNCHECKED: {"status": "ready", "tempo": None, "energy": 0.5, "camelot": None}}):
            with (
                self.subTest(movable=len(features)),
                patch("api.app.get_spotify_client", return_value=sp),
                patch.object(SpotifyPlaylistSorter, "_fetch_audio_features_local", return_value=features),
                TestClient(app) as client,
            ):
                session = Session(auth=Mock(), state="", user={"id": "listener"}, youtube_cookies="")
                app.state.sessions["test-session"] = session
                client.cookies.set(COOKIE, "test-session")
                headers = {"X-CSRF-Token": session.csrf}
                assert client.post(f"/api/playlists/{PLAYLIST}/analyze", headers=headers).status_code == 202
                job = client.get("/api/job").json()
                assert job["status"] == "ready"
                assert job["error"] is None
                assert len(job["tracks"]) == 5
                assert job["kept_count"] == 5 - len(features)
                assert [entry["name"] for entry in job["tracks"]] == [
                    "Unavailable item",
                    "Unavailable item",
                    "Local song",
                    "An episode",
                    "Uncertain song",
                ]
                assert [entry["kind"] for entry in job["tracks"]] == [
                    "unavailable",
                    "unavailable",
                    "local",
                    "episode",
                    "track",
                ]
                assert all(entry["bpm"] is None for entry in job["tracks"][:4])
                assert len({entry["occurrence"] for entry in job["tracks"]}) == 5
                assert job["sorted_tracks"] == []
                assert (
                    client.post(
                        "/api/job/sort",
                        headers=headers,
                        json={"revision": job["revision"], "first_occurrence": job["tracks"][-1]["occurrence"]},
                    ).status_code
                    == 422
                )
                assert (
                    client.post(
                        "/api/job/save",
                        headers=headers,
                        json={"revision": job["revision"]},
                    ).status_code
                    == 409
                )
        sp.playlist_reorder_items.assert_not_called()

    def test_entry_constraints_and_real_transition_neighbors(self) -> None:
        """Validate complete permutations before preview/save and assess only actual neighbors."""
        sp = Mock()
        sp.playlist.return_value = {"name": "Fixed opener", "snapshot_id": "snapshot"}
        sp.playlist_items.return_value = {
            "items": [
                {"item": None},
                spotify_item(FIRST, "First"),
                spotify_item(UNCHECKED, "Unknown"),
                spotify_item(SECOND, "Second"),
                {"track": spotify_item(FIRST, "First")["item"]},
            ],
            "next": None,
        }
        features: dict[str, dict[str, Any]] = {
            FIRST: {"status": "ready", "tempo": 120.0, "energy": 0.5, "camelot": "8B"},
            SECOND: {"status": "ready", "tempo": 122.0, "energy": 0.7, "camelot": "9B"},
            UNCHECKED: {"status": "error", "tempo": None, "energy": 0.5, "camelot": "8B"},
        }
        sorter = SpotifyPlaylistSorter(PLAYLIST, sp)
        for feature in features.values():
            if feature["status"] == "ready":
                feature["analysis"] = {
                    part: {"tempo": feature["tempo"], "evidence": {"tempo": 1.0}}
                    for part in ("intro", "outro", "body", "summary")
                }
        with patch.object(sorter, "_fetch_audio_features_local", return_value=features):
            sorter.load_playlist()
        original = sorter.current_order.copy()
        order = sorter.sort_playlist(last_occurrence=original[3])
        assert order == [original[i] for i in (0, 1, 2, 4, 3)]
        assert sorter.sort_playlist("foreign:snapshot:0") == []
        assert sorter.sort_playlist(original[4]) == []
        assert sorter.sort_playlist(original[0], original[3]) == order
        transitions = sorter.get_transition_analysis(order)
        assert [t["score"] is None for t in transitions] == [True, True, True, False]
        assert (transitions[-1]["track1_occurrence"], transitions[-1]["track2_occurrence"]) == tuple(order[-2:])
        assert transitions[-1]["bpm_diff"] == 2
        for invalid in (
            order[:-1],
            [*order[:-1], order[0]],
            [order[1], order[0], *order[2:]],
            [*order[:-1], "foreign:snapshot:0"],
        ):
            with self.subTest(invalid=invalid):
                assert not sorter.valid_order(invalid)
                assert all(frame.empty for frame in sorter.compare_playlists(invalid))
                assert sorter.get_transition_analysis(invalid) == []
                assert not sorter.update_spotify_playlist(invalid)[0]
        sp.playlist_reorder_items.assert_not_called()

    def test_profiles_optional_pins_and_noop_previews(self) -> None:
        """Bind profile/pin choices to a revision without reanalyzing or saving unchanged orders."""
        sp = Mock()
        sp.playlist.return_value = {"name": "Evening", "snapshot_id": "snapshot", "owner": {"id": "listener"}}
        sp.playlist_items.return_value = {
            "items": [spotify_item(FIRST, "First"), {"item": None}, spotify_item(SECOND, "Second")],
            "next": None,
        }
        features = {key: {"status": "ready", "tempo": None, "camelot": None, "energy": 0.5} for key in (FIRST, SECOND)}
        app = create_app()
        with (
            TestClient(app) as client,
            patch("api.app.get_spotify_client", return_value=sp),
            patch.object(SpotifyPlaylistSorter, "_fetch_audio_features_local", return_value=features) as analyze_audio,
        ):
            session = Session(auth=Mock(), state="", user={"id": "listener"}, youtube_cookies="")
            app.state.sessions["test-session"] = session
            client.cookies.set(COOKIE, "test-session")
            headers = {"X-CSRF-Token": session.csrf}
            client.post(f"/api/playlists/{PLAYLIST}/analyze", headers=headers)
            loaded = client.get("/api/job").json()
            assert (
                client.post("/api/job/sort", headers=headers, json={"revision": loaded["revision"]}).status_code == 202
            )
            original = client.get("/api/job").json()
            assert original["profile"] == "smooth"
            assert original["first_occurrence"] is None
            assert original["last_occurrence"] is None
            assert original["arrangement"]["unchanged"]
            assert original["arrangement"]["assessed_edges"] == 0
            assert (
                client.post("/api/job/save", headers=headers, json={"revision": original["revision"]}).status_code
                == 409
            )
            first = original["tracks"][0]["occurrence"]
            for invalid in (
                {"profile": "workout"},
                {"first_occurrence": "foreign"},
                {"first_occurrence": first, "last_occurrence": first},
                {"last_occurrence": original["tracks"][1]["occurrence"]},
            ):
                assert (
                    client.post(
                        "/api/job/sort", headers=headers, json={"revision": original["revision"], **invalid}
                    ).status_code
                    == 422
                )
            assert (
                client.post(
                    "/api/job/sort",
                    headers=headers,
                    json={
                        "revision": original["revision"],
                        "profile": "variety",
                        "last_occurrence": first,
                    },
                ).status_code
                == 202
            )
            variety = client.get("/api/job").json()
            assert variety["profile"] == "variety"
            assert variety["first_occurrence"] is None
            assert variety["last_occurrence"] == first
            assert [entry["id"] for entry in variety["sorted_tracks"]] == [SECOND, None, FIRST]
            assert not variety["arrangement"]["unchanged"]
            assert variety["arrangement"]["cost"] <= variety["arrangement"]["baseline_cost"]
            assert (
                client.post("/api/job/save", headers=headers, json={"revision": original["revision"]}).status_code
                == 409
            )
            analyze_audio.assert_called_once()
            sp.playlist_reorder_items.assert_not_called()

    def test_metadata_and_recording_progress_are_visible_before_completion(self) -> None:
        """Expose every entry during work, counting failed checks separately from success."""
        started, measuring, allow_measure, finish = Event(), Event(), Event(), Event()
        sp = Mock()
        sp.playlist.return_value = {"name": "Progress", "snapshot_id": "snapshot", "owner": {"id": "listener"}}
        sp.playlist_items.return_value = {
            "items": [
                spotify_item(FIRST, "First"),
                {"item": None},
                spotify_item(SECOND, "Second"),
                spotify_item(FIRST, "First"),
            ],
            "next": None,
        }

        def analyze(
            track: dict[str, Any], on_stage: Callable[[str], None] | None = None, **_kwargs: object
        ) -> dict[str, Any]:
            assert on_stage is not None
            on_stage("matching")
            if track["id"] == FIRST:
                started.set()
            assert allow_measure.wait(5)
            on_stage("analyzing")
            if track["id"] == FIRST:
                measuring.set()
            assert finish.wait(5)
            if track["id"] == SECOND:
                return {"status": "uncertain", "message": "Recording uncertain"}
            return {
                "status": "ready",
                "analysis": {"summary": {"rms_db": -20.0, "onset": 1.0, "tempo": 120.0, "camelot": None}},
            }

        app = create_app()
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("api.playlist_sorter._CACHE_FILE", Path(directory) / "cache.json"),
            patch("api.app.get_spotify_client", return_value=sp),
            patch.object(SpotifyPlaylistSorter, "_analyze_track", side_effect=analyze),
            TestClient(app) as client,
            ThreadPoolExecutor(max_workers=1) as requests,
        ):
            session = Session(auth=Mock(), state="", user={"id": "listener"}, youtube_cookies="")
            app.state.sessions["test-session"] = session
            client.cookies.set(COOKIE, "test-session")
            headers = {"X-CSRF-Token": session.csrf}
            request = requests.submit(client.post, f"/api/playlists/{PLAYLIST}/analyze", headers=headers)
            try:
                assert started.wait(5)
                pending = client.get("/api/job").json()
                assert pending["metadata_loaded"]
                assert pending["status"] == "analyzing"
                assert [entry["id"] for entry in pending["tracks"]] == [FIRST, None, SECOND, FIRST]
                assert pending["tracks"][0]["analysis_status"] == pending["tracks"][3]["analysis_status"] == "matching"
                assert pending["analyzed_count"] == 0
                assert pending["kept_count"] == 1
                assert pending["total"] == 3
                assert (
                    client.post("/api/job/sort", headers=headers, json={"revision": pending["revision"]}).status_code
                    == 409
                )
                allow_measure.set()
                assert measuring.wait(5)
                assert client.get("/api/job").json()["tracks"][0]["analysis_status"] == "analyzing"
            finally:
                allow_measure.set()
                finish.set()
                assert request.result(timeout=5).status_code == 202
            result = client.get("/api/job").json()
            assert result["status"] == "ready"
            assert result["completed"] == result["total"] == 3
            assert (result["analyzed_count"], result["kept_count"]) == (2, 2)
            assert result["tracks"][2]["analysis_status"] == "uncertain"
            assert result["tracks"][2]["fixed_reason"] == "Recording uncertain"
            assert result["tracks"][0]["key"] is None
            sp.playlist_reorder_items.assert_not_called()

    def test_interrupted_analysis_keeps_loaded_metadata(self) -> None:
        """A failed analysis retains the complete last-loaded order and stops pending labels."""
        sp = Mock()
        sp.playlist.return_value = {"name": "Progress", "snapshot_id": "snapshot", "owner": {"id": "listener"}}
        sp.playlist_items.return_value = {"items": [spotify_item(FIRST, "First"), {"item": None}], "next": None}
        app = create_app()
        with (
            TestClient(app) as client,
            patch("api.app.get_spotify_client", return_value=sp),
            patch.object(SpotifyPlaylistSorter, "_fetch_audio_features_local", side_effect=RuntimeError("Interrupted")),
        ):
            session = Session(auth=Mock(), state="", user={"id": "listener"}, youtube_cookies="")
            app.state.sessions["test-session"] = session
            client.cookies.set(COOKIE, "test-session")
            headers = {"X-CSRF-Token": session.csrf}
            client.post(f"/api/playlists/{PLAYLIST}/analyze", headers=headers)
            failed = client.get("/api/job").json()
            assert failed["status"] == "error"
            assert failed["metadata_loaded"]
            assert [entry["id"] for entry in failed["tracks"]] == [FIRST, None]
            assert failed["tracks"][0]["analysis_status"] == "error"
            assert failed["tracks"][0]["fixed_reason"] == "Check interrupted"
            assert (
                client.post("/api/job/save", headers=headers, json={"revision": failed["revision"]}).status_code == 409
            )
            sp.playlist_reorder_items.assert_not_called()

    def test_revoked_login_clears_the_browser_session(self) -> None:
        """A revoked refresh token must not leave the browser stuck in a login loop."""
        app = create_app()
        sp = Mock()
        sp.current_user_playlists.side_effect = SpotifyOauthError("invalid_grant", "Token expired")
        with TestClient(app) as client, patch("api.app.get_spotify_client", return_value=sp):
            app.state.sessions["test-session"] = Session(
                auth=Mock(), state="", user={"id": "listener"}, youtube_cookies=""
            )
            client.cookies.set(COOKIE, "test-session")
            assert client.get("/api/playlists").status_code == 401
            assert client.get("/api/session").json()["user"] is None
            assert client.get("/api/job").status_code == 401

    def test_localhost_login_sets_the_cookie_on_the_callback_host(self) -> None:
        """Normalize the hostname before OAuth so the callback receives its session cookie."""
        for port in (8000, 5178):
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
                    with patch("api.app.get_spotify_client", return_value=sp):
                        session = next(iter(app.state.sessions.values()))
                        session.auth.get_access_token = Mock(return_value="test-token")
                        response = client.get(
                            callback, params={"code": "test", "state": query["state"][0]}, follow_redirects=False
                        )
                    assert response.headers["location"] == "/playlists"
