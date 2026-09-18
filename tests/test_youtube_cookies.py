"""Offline checks for private cookie sources in search, download and HTTP settings."""

# ruff: noqa: INP001, SLF001, PT027

from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from yt_dlp.cookies import YDLLogger, YoutubeDLCookieJar

from api import playlist_sorter, youtube
from api.app import COOKIE, Job, JobView, Session, create_app

COOKIES = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t4102444800\tSID\tprivate-cookie\n"
UNRELATED = ".example.com\tTRUE\t/\tTRUE\t4102444800\tsecret\tunrelated-secret\n"
ENV = {"YOUTUBE_COOKIES_FILE": "", "YOUTUBE_BROWSER": "", "YOUTUBE_BROWSER_PROFILE": "", "YOUTUBE_BROWSER_KEYRING": ""}


class YoutubeCookiesTest(unittest.TestCase):
    """Exercise yt-dlp parsing with fake cookie jars; never open real browser profiles."""

    def test_no_cookie_configuration_continues_anonymously(self) -> None:
        """Neither an export nor a browser profile is required to use yt-dlp."""
        with patch.dict(os.environ, ENV), patch("yt_dlp.cookies.extract_cookies_from_browser") as browser:
            text = youtube.configured_cookies()
            assert text == ""
            options = youtube.youtube_options(text)
            assert "cookiefile" not in options
            assert "cookiesfrombrowser" not in options
            with playlist_sorter.yt_dlp.YoutubeDL(options) as downloader:
                assert downloader.cookiejar.get_cookie_header("https://www.youtube.com/") is None
            browser.assert_not_called()

    def test_file_source_stays_read_only_and_download_reuses_video_info(self) -> None:
        """All stages receive independent jars; downloading never reextracts a selected URL."""
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, ENV):
            path = Path(directory) / "cookies.txt"
            path.write_text(COOKIES + UNRELATED)
            path.chmod(0o400)
            os.environ["YOUTUBE_COOKIES_FILE"] = str(path)
            seen = []
            source = {"id": "abcdefghijk", "title": "Artist - Test", "duration": 1, "artist": "Artist"}

            def extract(ydl: playlist_sorter.yt_dlp.YoutubeDL, url: str, *, download: bool) -> dict[str, Any]:
                assert not download
                seen.append(ydl.cookiejar.get_cookie_header("https://www.youtube.com/"))
                assert ydl.cookiejar.get_cookie_header("https://example.com/") is None
                return {"entries": [source]} if url.startswith("ytsearch") else source

            def process(
                ydl: playlist_sorter.yt_dlp.YoutubeDL, info: dict[str, Any], *, download: bool
            ) -> dict[str, Any]:
                assert info["id"] == source["id"]
                assert download
                assert ydl.params["format"] == "bestaudio"
                assert ydl.params["skip_unavailable_fragments"] is False
                seen.append(ydl.cookiejar.get_cookie_header("https://www.youtube.com/"))
                output = ydl.params["outtmpl"]["default"] % {"ext": "wav"}
                Path(output).touch()
                return info

            with (
                patch.object(playlist_sorter.yt_dlp.YoutubeDL, "extract_info", autospec=True, side_effect=extract),
                patch.object(playlist_sorter.yt_dlp.YoutubeDL, "process_ie_result", autospec=True, side_effect=process),
                patch.object(playlist_sorter, "load_audio", return_value=(playlist_sorter.np.zeros(1), 1)),
                patch.object(playlist_sorter, "analyze_sections", return_value={}),
            ):
                result = playlist_sorter.SpotifyPlaylistSorter._analyze_track(
                    {"id": "test", "Track": "Test", "Artist": "Artist", "duration_ms": 1000}
                )
            assert result["status"] == "ready"
            assert seen == ["SID=private-cookie"] * 3
            assert path.read_text() == COOKIES + UNRELATED

    def test_browser_is_loaded_once_per_job_and_errors_are_visible(self) -> None:
        """Honor the configured browser/profile and stop when decryption is incomplete."""
        jar = YoutubeDLCookieJar(io.StringIO(COOKIES + UNRELATED))
        jar.load()
        env = {
            **ENV,
            "YOUTUBE_BROWSER": "chrome",
            "YOUTUBE_BROWSER_PROFILE": "Default",
            "YOUTUBE_BROWSER_KEYRING": "gnomekeyring",
        }
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, env),
            patch.object(playlist_sorter, "_CACHE_FILE", Path(directory) / "cache.json"),
            patch("yt_dlp.cookies.extract_cookies_from_browser", return_value=jar) as browser,
            patch.object(
                playlist_sorter.SpotifyPlaylistSorter, "_analyze_track", return_value={"status": "uncertain"}
            ) as analyze,
        ):
            sorter = playlist_sorter.SpotifyPlaylistSorter("playlist", Mock())
            sorter._fetch_audio_features_local([{"id": key, "Track": "Test"} for key in ("a", "b", "a")])
            browser.assert_called_once()
            assert browser.call_args.args[:2] == ("chrome", "Default")
            assert browser.call_args.kwargs["keyring"] == "GNOMEKEYRING"
            assert analyze.call_count == 2
            for call in analyze.call_args_list:
                assert "private-cookie" in call.kwargs["cookie_text"]
                assert "unrelated-secret" not in call.kwargs["cookie_text"]
            browser.side_effect = OSError("private-path-and-secret")
            with self.assertRaises(youtube.SourceAccessError) as caught:
                youtube.configured_cookies()
            assert "private-path" not in str(caught.exception)
            browser.side_effect = None

            def partial(*_args: object, logger: YDLLogger, **_kwargs: object) -> YoutubeDLCookieJar:
                logger.warning("failed to decrypt cookie", only_once=True)
                return jar

            browser.side_effect = partial
            with self.assertRaises(youtube.SourceAccessError):
                youtube.configured_cookies()

    def test_cookie_validation_never_prints_credentials(self) -> None:
        """Reject malformed, expired and unrelated exports without yt-dlp's raw-line warnings."""
        for text in (
            '{"token":"secret"}',
            COOKIES + "private-secret\n",
            COOKIES.replace("4102444800", "1"),
            COOKIES.replace("youtube.com", "evilyoutube.com"),
        ):
            with self.subTest(text=text), contextlib.redirect_stderr(io.StringIO()) as stderr:
                with self.assertRaises(youtube.SourceAccessError):
                    youtube.validate_cookie_text(text)
                assert stderr.getvalue() == ""
        assert "private-cookie" in youtube.validate_cookie_text(COOKIES.replace("4102444800", "0"))
        with (
            patch.dict(os.environ, {**ENV, "YOUTUBE_COOKIES_FILE": "/missing-cookie-file"}),
            self.assertRaises(youtube.SourceAccessError),
        ):
            youtube.configured_cookies()

    def test_uploaded_cookies_are_session_scoped_and_never_returned(self) -> None:
        """Bind changes to CSRF, block them during work, and discard credentials on logout."""
        app = create_app()
        with TestClient(app) as client, patch.dict(os.environ, ENV):
            session = Session(auth=Mock(), state="", user={"id": "listener"})
            other = Session(auth=Mock(), state="", user={"id": "other"})
            app.state.sessions.update({"one": session, "two": other})
            client.cookies.set(COOKIE, "one")
            headers = {"X-CSRF-Token": session.csrf}
            body = {"mode": "upload", "cookies": COOKIES + UNRELATED}
            assert client.post("/api/youtube", json=body).status_code == 403
            response = client.post("/api/youtube", headers=headers, json=body)
            assert response.status_code == 200
            assert response.json()["mode"] == "upload"
            assert "private-cookie" not in response.text
            assert session.youtube_cookies
            assert "unrelated-secret" not in session.youtube_cookies
            assert client.get("/api/youtube").headers["cache-control"] == "no-store"
            client.cookies.set(COOKIE, "two")
            assert client.get("/api/youtube").json()["mode"] == "server"
            assert other.youtube_cookies is None
            client.cookies.set(COOKIE, "one")
            assert (
                client.post("/api/youtube", headers=headers, json={"mode": "upload", "cookies": "secret"}).status_code
                == 422
            )
            assert (
                client.post(
                    "/api/youtube", headers=headers, json={"mode": "upload", "cookies": "x" * 262145}
                ).status_code
                == 422
            )
            session.job = Job(
                playlist_sorter.SpotifyPlaylistSorter("playlist", Mock()), JobView(playlist_id="playlist")
            )
            assert client.post("/api/youtube", headers=headers, json=body).status_code == 409
            session.job = None
            assert client.post("/api/youtube", headers=headers, json={"mode": "anonymous"}).status_code == 200
            assert session.youtube_cookies == ""
            client.post("/api/auth/logout", headers=headers)
            assert client.get("/api/youtube").status_code == 401
