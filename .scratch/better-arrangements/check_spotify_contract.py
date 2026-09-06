"""Probe the installed Spotify SDK with fake HTTP responses and no network.

Run from the repository root:
    PYTHONPATH=. uv run python .scratch/better-arrangements/check_spotify_contract.py
"""

import json
import logging
from importlib.metadata import version
from unittest.mock import Mock, patch

from requests import Response
from spotipy import SpotifyException

from app.playlist_sorter import SpotifyPlaylistSorter
from app.spotify_auth import get_all_playlists, get_spotify_client

PLAYLIST = "p" * 22
TRACK = "a" * 22
BASE = "https://api.spotify.com/v1/"


def response(body: object, status: int = 200) -> Response:
    """Create a real requests response without issuing a request."""
    result = Response()
    result.status_code = status
    result.url = BASE + f"playlists/{PLAYLIST}/items"
    result._content = json.dumps(body).encode()
    return result


def main() -> None:
    """Check endpoint paths, field parsing, moves and quota error propagation."""
    auth = Mock()
    auth.get_access_token.return_value = "offline-test-token"
    sp = get_spotify_client(auth)
    assert sp.retries == sp.status_retries == 0
    logging.getLogger("spotipy.client").setLevel(logging.CRITICAL)
    with (
        patch("socket.socket.connect", side_effect=AssertionError("Network is disabled")),
        patch("requests.sessions.Session.request") as transport,
    ):
        for field in ("items", "tracks"):
            transport.return_value = response(
                {
                    "items": [
                        {
                            "id": PLAYLIST,
                            "name": "Offline",
                            "owner": {"id": "owner", "display_name": None},
                            "images": [],
                            "description": None,
                            field: {"total": 5},
                        }
                    ],
                    "next": None,
                }
            )
            assert get_all_playlists(sp, "owner") == [{"id": PLAYLIST, "name": "Offline", "total": 5, "image": None}]
            assert transport.call_args.args == ("GET", BASE + "me/playlists")
            assert transport.call_args.kwargs["params"]["limit"] == 50

        for field in ("item", "track"):
            track = {"id": TRACK, "name": "Offline", "artists": [], "album": None, "type": "track"}
            next_page = BASE + f"playlists/{PLAYLIST}/items?offset=50"
            transport.reset_mock()
            transport.side_effect = [
                response({"items": [{field: track}, {field: None}], "next": next_page}),
                response(
                    {
                        "items": [
                            {field: track},
                            {field: {**track, "is_local": True}},
                            {field: {"id": "e" * 22, "type": "episode"}},
                        ],
                        "next": None,
                    }
                ),
            ]
            sorter = SpotifyPlaylistSorter(PLAYLIST, sp)
            tracks = sorter._fetch_tracks_from_spotify()
            assert [entry["id"] for entry in tracks] == [TRACK, TRACK]
            assert len(sorter.original_items) == 5
            assert [entry["fixed_reason"] for entry in sorter.original_items] == [
                None,
                "Unavailable on Spotify",
                None,
                "Local file",
                "Episode",
            ]
            assert tracks[0]["duration_ms"] is None and tracks[0]["Popularity"] is None
            assert transport.call_args_list[0].args == ("GET", BASE + f"playlists/{PLAYLIST}/items")
            assert transport.call_args_list[0].kwargs["params"]["limit"] == 50
            assert transport.call_args_list[1].args == ("GET", next_page)

        transport.side_effect = None
        transport.return_value = response({"snapshot_id": "after"})
        assert sp.playlist_reorder_items(PLAYLIST, 2, 0, snapshot_id="before") == {"snapshot_id": "after"}
        assert transport.call_args.args == ("PUT", BASE + f"playlists/{PLAYLIST}/items")
        assert json.loads(transport.call_args.kwargs["data"]) == {
            "range_start": 2,
            "range_length": 1,
            "insert_before": 0,
            "snapshot_id": "before",
        }

        transport.reset_mock()
        quota = response({"error": {"status": 429, "message": "Too many requests", "reason": "QUOTA_EXCEEDED"}}, 429)
        quota.headers["Retry-After"] = "30"
        transport.return_value = quota
        try:
            sp.playlist_reorder_items(PLAYLIST, 2, 0, snapshot_id="before")
        except SpotifyException as exc:
            assert exc.http_status == 429 and exc.reason == "QUOTA_EXCEEDED"
            assert exc.headers["Retry-After"] == "30"
        else:
            raise AssertionError("Quota failure must propagate")
        assert transport.call_count == 1
    print(
        f"Spotipy {version('spotipy')}: endpoint, pagination, nullable-item, move-payload and quota checks passed offline."
    )


if __name__ == "__main__":
    main()
