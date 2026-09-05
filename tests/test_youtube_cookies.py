"""Offline checks for optional YouTube cookies in search and download."""

# ruff: noqa: INP001

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import playlist_sorter


class YoutubeCookiesTest(unittest.TestCase):
    """Exercise real yt-dlp cookie loading without network or ffmpeg."""

    def test_cookies_are_optional_and_source_stays_unchanged(self) -> None:
        """Use cookies in both phases without writing back to the source file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cookies = Path(tmpdir) / "cookies.txt"
            contents = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t4102444800\tSID\ttest-cookie\n"
            cookies.write_text(contents, encoding="utf-8")
            cookies.chmod(0o400)
            seen: list[tuple[bool, str | None]] = []
            for cookie_path in (None, "", str(Path(tmpdir) / "missing.txt"), tmpdir, str(cookies)):
                with self.subTest(cookie_path=cookie_path), patch.dict(os.environ):
                    os.environ.pop("YOUTUBE_COOKIES_FILE", None)
                    if cookie_path is not None:
                        os.environ["YOUTUBE_COOKIES_FILE"] = cookie_path
                    expected = "SID=test-cookie" if cookie_path == str(cookies) else None
                    seen.clear()

                    def extract_info(ydl: playlist_sorter.yt_dlp.YoutubeDL, url: str, *, download: bool) -> dict:
                        seen.append((download, ydl.cookiejar.get_cookie_header("https://www.youtube.com/")))
                        if download:
                            assert url == "https://www.youtube.com/watch?v=test"
                            output = ydl.params["outtmpl"]["default"] % {"id": "test", "ext": "wav"}
                            Path(output).touch()
                        return {"webpage_url": "https://www.youtube.com/watch?v=test"}

                    audio = (playlist_sorter.np.zeros(1), 22050)
                    with (
                        patch.object(
                            playlist_sorter.yt_dlp.YoutubeDL, "extract_info", autospec=True, side_effect=extract_info
                        ),
                        patch.object(playlist_sorter, "_load_audio", return_value=audio),
                    ):
                        result = playlist_sorter.SpotifyPlaylistSorter._download_and_load(  # noqa: SLF001
                            "ytsearch1:test", "test", "spotify-test", None
                        )
                    assert result is audio
                    assert seen == [(False, expected), (True, expected)]
                    assert cookies.read_text(encoding="utf-8") == contents
