"""Spotify OAuth with server-only credentials and a cache per browser session."""

from __future__ import annotations

import os
from typing import Any

import spotipy
from spotipy.cache_handler import MemoryCacheHandler
from spotipy.oauth2 import SpotifyOAuth

SPOTIFY_SCOPE = "playlist-modify-public playlist-modify-private playlist-read-private playlist-read-collaborative"


def is_configured() -> bool:
    """Return whether the server has Spotify credentials."""
    return bool(os.getenv("SPOTIFY_CLIENT_ID") and os.getenv("SPOTIFY_CLIENT_SECRET"))


def get_redirect_uri() -> str:
    """Use the public browser origin, including Vite's port during development."""
    return os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:5178/api/auth/callback")


def get_auth_manager(state: str) -> SpotifyOAuth:
    """Create an isolated OAuth cache; never write tokens to disk."""
    return SpotifyOAuth(
        client_id=os.environ["SPOTIFY_CLIENT_ID"],
        client_secret=os.environ["SPOTIFY_CLIENT_SECRET"],
        redirect_uri=get_redirect_uri(),
        scope=SPOTIFY_SCOPE,
        state=state,
        cache_handler=MemoryCacheHandler(),
        open_browser=False,
        requests_timeout=15,
    )


def get_spotify_client(auth: SpotifyOAuth) -> spotipy.Spotify:
    """Let Spotipy refresh tokens in this session's memory cache."""
    # Reordering must not be replayed automatically after an ambiguous network failure.
    return spotipy.Spotify(auth_manager=auth, requests_timeout=15, retries=0, status_retries=0)


def get_all_playlists(sp: spotipy.Spotify, user_id: str) -> list[dict[str, Any]]:
    """Return owned and collaborative playlists, following all pages."""
    playlists = []
    results = sp.current_user_playlists(limit=50)
    while results:
        for playlist in results["items"]:
            if not playlist:
                continue
            if playlist.get("owner", {}).get("id") != user_id and not playlist.get("collaborative"):
                continue
            images = playlist.get("images") or []
            playlists.append(
                {
                    "id": playlist["id"],
                    "name": playlist["name"],
                    "total": (playlist.get("items") or playlist.get("tracks") or {}).get("total", 0),
                    "image": images[0]["url"] if images else None,
                }
            )
        results = sp.next(results) if results.get("next") else None
    return playlists
