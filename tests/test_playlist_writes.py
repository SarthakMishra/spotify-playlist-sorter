"""Offline save/restore contracts using a mutable, paginated Spotify playlist."""

# ruff: noqa: INP001

from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from typing import Any, override
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from api.app import COOKIE, Job, JobView, Session, _tracks, create_app
from api.playlist_sorter import SpotifyPlaylistSorter

PLAYLIST = "p" * 22


class PlaylistWritesTest(unittest.TestCase):
    """Verify every page, duplicate occurrence and fixed placeholder before confirming writes."""

    @override
    def setUp(self) -> None:
        """Keep provider state independent of the sorter's expected order."""
        self.items: list[dict[str, Any] | None] = [
            {"item": {"id": "a", "uri": "spotify:track:a"}, "added_at": "first-copy"},
            {"item": {"id": "unchecked", "uri": "spotify:track:unchecked"}},
            {"item": {"id": "b", "uri": "spotify:track:b"}},
            None,
            {"item": {"id": "a", "uri": "spotify:track:a"}, "added_at": "second-copy"},
            {"item": {"uri": "spotify:local:artist:album:song:180"}, "is_local": True},
            {"item": {"id": "episode", "uri": "spotify:episode:episode", "type": "episode"}},
        ]
        self.original = self.items.copy()
        self.version = 0
        self.sp = Mock()
        self.sp.playlist.side_effect = lambda *_, **__: {
            "snapshot_id": str(self.version),
            "name": "Test playlist",
            "owner": {"id": "listener"},
        }
        self.sp.playlist_items.side_effect = lambda *_: {"items": self.items[:3], "next": "page-two"}
        self.sp.next.side_effect = lambda *_: {"items": self.items[3:], "next": None}
        self.sp.playlist_reorder_items.side_effect = self.move
        self.sorter = SpotifyPlaylistSorter(PLAYLIST, self.sp)
        features = {key: {"status": "ready"} for key in ("a", "b")}
        with patch.object(self.sorter, "_fetch_audio_features_local", return_value=features):
            self.sorter.load_playlist()
        self.order = self.sorter.current_order.copy()
        self.target = [self.order[i] for i in (2, 1, 0, 3, 4, 5, 6)]

    @override
    def tearDown(self) -> None:
        """No test may replace a playlist or add its contents again."""
        self.sp.playlist_replace_items.assert_not_called()
        self.sp.playlist_add_items.assert_not_called()

    def move(self, _playlist: str, source: int, destination: int, **kwargs: object) -> dict[str, str]:
        """Apply a single provider move and issue its next snapshot."""
        assert kwargs["snapshot_id"] == str(self.version)
        self.items.insert(destination, self.items.pop(source))
        self.version += 1
        return {"snapshot_id": str(self.version)}

    def test_verified_save_and_latest_restore(self) -> None:
        """Restore the most recent pre-save order, retaining duplicates and opaque items."""
        assert self.sorter.update_spotify_playlist(self.target)[0]
        assert self.items == [self.original[i] for i in (2, 1, 0, 3, 4, 5, 6)]
        previous = self.items.copy()
        second = [self.order[i] for i in (4, 1, 0, 3, 2, 5, 6)]
        assert self.sorter.update_spotify_playlist(second)[0]
        assert self.sorter.restore_order == self.target
        # Previewing different endpoint choices must not change the restore target.
        self.sorter.sort_playlist(first_occurrence=self.order[0])
        assert self.sorter.can_restore
        assert self.sorter.restore_spotify_playlist()[0]
        assert self.items == previous
        assert self.sorter.current_order == self.target
        assert self.sorter.snapshot_id == str(self.version)
        assert not self.sorter.can_restore
        self.sp.playlist_reorder_items.reset_mock()
        assert not self.sorter.restore_spotify_playlist()[0]
        self.sp.playlist_reorder_items.assert_not_called()

    def test_external_edit_prevents_save_or_restore(self) -> None:
        """A later provider snapshot invalidates both actions before any move."""
        assert self.sorter.update_spotify_playlist(self.target)[0]
        self.sp.playlist_reorder_items.reset_mock()
        self.version += 1
        success, message = self.sorter.restore_spotify_playlist()
        assert not success
        assert "changed on Spotify" in message
        assert self.sorter.snapshot_id is None
        assert not self.sorter.can_restore
        assert not self.sorter.update_spotify_playlist(self.order)[0]
        self.sp.playlist_reorder_items.assert_not_called()

    def test_source_order_must_match_before_writing(self) -> None:
        """A stale or incomplete initial read cannot be used to calculate provider moves."""
        self.items.pop()
        assert not self.sorter.update_spotify_playlist(self.target)[0]
        assert self.sorter.snapshot_id is None
        assert not self.sorter.can_restore
        self.sp.playlist_reorder_items.assert_not_called()

    def test_save_and_restore_stay_busy_until_verification_finishes(self) -> None:
        """Serialize session actions and expose restore only after a complete successful read."""
        reading, finish = Event(), Event()

        def read_page(*_: object) -> dict[str, Any]:
            if self.version > starting_version:
                reading.set()
                assert finish.wait(5)
            return {"items": self.items[3:], "next": None}

        self.sp.next.side_effect = read_page
        app = create_app()
        with TestClient(app) as client, ThreadPoolExecutor(max_workers=1) as requests:
            job = Job(
                self.sorter,
                JobView(
                    playlist_id=PLAYLIST,
                    status="ready",
                    sorted_tracks=_tracks(self.sorter.compare_playlists(self.target)[1]),
                ),
                self.target,
            )
            session = Session(auth=Mock(), state="", user={"id": "listener"}, job=job)
            app.state.sessions["test"] = session
            client.cookies.set(COOKIE, "test")
            headers = {"X-CSRF-Token": session.csrf}
            for action, working, complete in (("save", "saving", "saved"), ("restore", "restoring", "restored")):
                reading.clear()
                finish.clear()
                starting_version = self.version
                request = requests.submit(
                    client.post, f"/api/job/{action}", headers=headers, json={"revision": job.view.revision}
                )
                try:
                    assert reading.wait(5)
                    pending = client.get("/api/job").json()
                    assert pending["status"] == working
                    assert not pending["can_restore"]
                    for blocked in ("save", "sort", "restore"):
                        assert (
                            client.post(
                                f"/api/job/{blocked}", headers=headers, json={"revision": pending["revision"]}
                            ).status_code
                            == 409
                        )
                    assert client.post(f"/api/playlists/{PLAYLIST}/analyze", headers=headers).status_code == 409
                finally:
                    finish.set()
                    assert request.result(timeout=5).status_code == 202
                result = client.get("/api/job").json()
                assert result["status"] == complete
                assert result["can_restore"] == (action == "save")
            assert client.post("/api/auth/logout", headers=headers).status_code == 200
            assert (
                client.post("/api/job/restore", headers=headers, json={"revision": job.view.revision}).status_code
                == 401
            )

    def test_partial_move_and_lost_response_are_never_replayed(self) -> None:
        """A second move can succeed remotely and still fail locally; require a fresh check."""

        def lose_response(playlist: str, source: int, destination: int, **kwargs: object) -> dict[str, str]:
            response = self.move(playlist, source, destination, **kwargs)
            if self.version == 2:
                message = "Response lost"
                raise TimeoutError(message)
            return response

        self.sp.playlist_reorder_items.side_effect = lose_response
        assert not self.sorter.update_spotify_playlist(self.target)[0]
        assert self.items != self.original
        assert self.sorter.current_order == self.order
        assert self.sorter.snapshot_id is None
        assert not self.sorter.can_restore
        count = self.sp.playlist_reorder_items.call_count
        assert count == 2
        assert not self.sorter.update_spotify_playlist(self.target)[0]
        assert not self.sorter.restore_spotify_playlist()[0]
        assert self.sp.playlist_reorder_items.call_count == count

    def test_missing_snapshot_stops_before_another_move(self) -> None:
        """Never continue a multi-move write without its next snapshot constraint."""
        self.sp.playlist_reorder_items.return_value = {"snapshot_id": None}
        self.sp.playlist_reorder_items.side_effect = None
        assert not self.sorter.update_spotify_playlist(self.target)[0]
        self.sp.playlist_reorder_items.assert_called_once()
        assert self.sorter.snapshot_id is None
        assert not self.sorter.can_restore

    def test_changed_or_incorrect_readback_never_confirms_a_save(self) -> None:
        """Even a successful move response cannot confirm a torn, incomplete or wrong read."""
        for fault in ("snapshot", "missing", "duplicate", "fixed", "response"):
            with self.subTest(fault=fault):
                self.setUp()

                def read_page(*_: object, fault: str = fault) -> dict[str, Any]:
                    items = self.items[3:].copy()
                    if self.version:
                        if fault == "snapshot":
                            self.version += 1
                        elif fault == "missing":
                            items.pop()
                        elif fault == "duplicate":
                            items[1] = self.original[0]
                        elif fault == "fixed":
                            items[0], items[2] = items[2], items[0]
                        else:
                            message = "Readback unavailable"
                            raise TimeoutError(message)
                    return {"items": items, "next": None}

                self.sp.next.side_effect = read_page
                app = create_app()
                with TestClient(app) as client:
                    job = Job(
                        self.sorter,
                        JobView(
                            playlist_id=PLAYLIST,
                            status="ready",
                            sorted_tracks=_tracks(self.sorter.compare_playlists(self.target)[1]),
                        ),
                        self.target,
                    )
                    session = Session(auth=Mock(), state="", user={"id": "listener"}, job=job)
                    app.state.sessions["test"] = session
                    client.cookies.set(COOKIE, "test")
                    assert (
                        client.post(
                            "/api/job/save",
                            json={"revision": job.view.revision},
                            headers={"X-CSRF-Token": session.csrf},
                        ).status_code
                        == 202
                    )
                    failed = client.get("/api/job").json()
                    assert failed["status"] == "error"
                    assert not failed["can_restore"]
                    assert "Some songs may have moved" in failed["error"]
                    assert self.sorter.snapshot_id is None
                self.tearDown()

    def test_restore_failure_and_new_analysis_remove_eligibility(self) -> None:
        """A fresh check loses history; an uncertain restore cannot be retried."""
        assert self.sorter.update_spotify_playlist(self.target)[0]
        with patch.object(
            self.sorter,
            "_fetch_audio_features_local",
            return_value={"a": {"status": "ready"}, "b": {"status": "ready"}},
        ):
            self.sorter.load_playlist()
        assert not self.sorter.can_restore
        # Use this check's new occurrence IDs, then interrupt its restore.
        order = self.sorter.current_order.copy()
        target = [order[i] for i in (4, 1, 2, 3, 0, 5, 6)]
        assert self.sorter.update_spotify_playlist(target)[0]
        self.sp.playlist_reorder_items.side_effect = TimeoutError("Connection lost")
        assert not self.sorter.restore_spotify_playlist()[0]
        assert not self.sorter.can_restore
        assert self.sorter.snapshot_id is None
