"""Recording-resolution regressions with invented metadata and no external requests."""

# ruff: noqa: INP001, SLF001

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import numpy as np
import yt_dlp

from app import playlist_sorter

TRACK = {"id": "a", "Track": "Example", "Artist": "Artist", "album": "Album", "duration_ms": 180000}
SOURCE = {"id": "abcdefghijk", "title": "Artist - Example", "duration": 180, "artist": "Artist"}


class RecordingPipelineTest(unittest.TestCase):
    """Catch false uncertainty and excessive candidate extraction at the recording boundary."""

    def test_best_effort_accepts_official_soundtracks_with_incomplete_credits(self) -> None:
        """Replay observed official uploads with absent credits or modest duration differences."""
        cases = [
            (
                "Girls Like To Swing",
                ["Sunidhi Chauhan"],
                243165,
                "DMo4zpGowAg",
                "'Girls Like To Swing' Full Song with LYRICS | Dil Dhadakne Do | T-Series",
                243,
                "T-Series",
            ),
            (
                "Jagga Jiteya",
                ["Kumaar", "Daler Mehndi", "Dee MC", "Shashwat Sachdev"],
                191489,
                "_d5fP57qc34",
                "Jagga Jiteya - Full Audio | URI | Daler Mehndi, Dee MC, Shashwat Sachdev",
                201,
                "Zee Music Company",
            ),
            (
                "Dhaakad",
                ["Raftaar", "Pritam"],
                176603,
                "GZvWFsSIQkI",
                "Dhaakad - Full Audio | Dangal | Pritam | Raftaar",
                188,
                "Zee Music Company",
            ),
        ]
        for title, artists, duration_ms, source_id, upload, duration, channel in cases:
            metadata = {"id": "a", "title": title, "artists": artists, "duration_ms": duration_ms}
            source = {
                "id": source_id,
                "title": upload,
                "duration": duration,
                "channel": channel,
                "channel_is_verified": True,
            }
            with self.subTest(title=title):
                assert playlist_sorter._shortlist([source], metadata)
                assert (
                    playlist_sorter._select_recording(playlist_sorter._rank_recordings([source], metadata)) is not None
                )

    def test_best_effort_chooses_a_close_match_instead_of_rejecting_ties(self) -> None:
        """The owner prefers the best eligible upload when several recordings are plausible."""
        metadata = {"id": "a", "title": "In Da Club", "artists": ["50 Cent"], "duration_ms": 193466}
        entries = [
            {"id": "abcdefghijk", "title": "50 Cent - In Da Club (Official Audio)", "duration": 193},
            {"id": "lmnopqrstuv", "title": "50 Cent - In Da Club (Lyrics)", "duration": 193},
        ]
        ranked = playlist_sorter._rank_recordings(entries, metadata)
        assert len(ranked) == 2
        assert playlist_sorter._select_recording(ranked) is not None

    def test_real_search_titles_keep_promising_audio_and_secondary_credits_are_optional(self) -> None:
        """Artist suffixes, album decoration and missing producer credits do not hide the song."""
        metadata = {"id": "a", "title": "Tension", "artists": ["Diljit Dosanjh"], "duration_ms": 168200}
        source = {
            "id": "ocN2bmt4UHk",
            "title": "Tension (Official Audio) Advisory | Diljit Dosanjh",
            "duration": 169,
            "channel": "Diljit Dosanjh",
        }
        assert playlist_sorter._shortlist([source], metadata)
        assert playlist_sorter._select_recording(playlist_sorter._rank_recordings([source], metadata)) is not None
        metadata = {"id": "a", "title": "For A Reason", "artists": ["Karan Aujla", "Ikky"], "duration_ms": 180000}
        source = {
            "id": "abcdefghijk",
            "title": "For A Reason (Official Audio) Karan Aujla",
            "duration": 180,
            "artist": "Karan Aujla",
        }
        assert playlist_sorter._select_recording(playlist_sorter._rank_recordings([source], metadata)) is not None

    def test_album_music_metadata_resolves_duplicate_upload_ambiguity(self) -> None:
        """An exact credited album upload supplies stronger evidence than an uncredited copy."""
        official = {
            **SOURCE,
            "title": "Example",
            "track": "Example",
            "artists": ["Artist"],
            "album": "Album",
            "channel": "Artist - Topic",
        }
        entries: list[dict[str, Any]] = [
            official,
            {**SOURCE, "id": "lmnopqrstuv", "artist": None, "channel": "Music fan"},
        ]

        def extract(url: str, **_kwargs: object) -> dict[str, Any]:
            return (
                {"entries": entries}
                if url.startswith("ytsearch")
                else next(entry for entry in entries if url.endswith(entry["id"]))
            )

        with (
            patch.object(yt_dlp.YoutubeDL, "extract_info", side_effect=extract),
            patch.object(playlist_sorter.SpotifyPlaylistSorter, "_download_and_load", return_value=(np.zeros(180), 1)),
            patch.object(playlist_sorter, "analyze_audio", return_value={"summary": {}}),
        ):
            result = playlist_sorter.SpotifyPlaylistSorter._analyze_track(TRACK, cookie_text="")
            assert result["status"] == "ready", result

    def test_search_does_not_extract_every_video(self) -> None:
        """Exercise yt-dlp's real playlist processing and count hydrated search candidates."""
        hydrated = []

        def extract(ydl: yt_dlp.YoutubeDL, url: str, *_args: object, **_kwargs: object) -> dict[str, Any]:
            if url.startswith("ytsearch"):
                return ydl.process_ie_result(
                    {
                        "_type": "playlist",
                        "id": "search",
                        "extractor": "youtube:search",
                        "extractor_key": "YoutubeSearch",
                        "webpage_url": url,
                        "entries": [
                            {
                                "_type": "url",
                                "ie_key": "Youtube",
                                "url": f"https://www.youtube.com/watch?v=abcdefghij{i}",
                                "id": f"abcdefghij{i}",
                                "title": "Artist - Example" if i == 0 else "Different song",
                                "duration": 180,
                                "channel": "Artist",
                            }
                            for i in range(10)
                        ],
                    },
                    download=False,
                )
            hydrated.append(url)
            return {
                **SOURCE,
                "id": url.rsplit("=", 1)[-1],
                "title": "Artist - Example" if url.endswith("0") else "Different song",
            }

        with (
            patch.object(yt_dlp.YoutubeDL, "extract_info", autospec=True, side_effect=extract),
            patch.object(playlist_sorter.SpotifyPlaylistSorter, "_download_and_load", return_value=(np.zeros(180), 1)),
            patch.object(playlist_sorter, "analyze_audio", return_value={"summary": {}}),
        ):
            result = playlist_sorter.SpotifyPlaylistSorter._analyze_track(TRACK, cookie_text="")
            assert result["status"] == "ready", result
            assert len(hydrated) <= 3, f"Hydrated {len(hydrated)} candidates for one recording"

    def test_structured_metadata_keeps_credits_and_version_conflicts(self) -> None:
        """Ignore featured-artist display suffixes only when full credits support the match."""
        metadata = {
            "id": "a",
            "title": "Example (feat. Guest)",
            "artists": ["Artist", "Guest"],
            "album": "Album",
            "duration_ms": 180000,
        }
        source = {**SOURCE, "track": "Example", "artists": ["Artist", "Guest"], "album": "Album"}
        ranked = playlist_sorter._rank_recordings([source], metadata)
        assert playlist_sorter._select_recording(ranked) is not None
        for changed in (
            {**source, "artists": ["Someone else"]},
            {**source, "title": "Artist - Example (Live)"},
            {**source, "title": "Artist - Example (feat. Guest) (Live)"},
            {**source, "title": "Artist - Example feat. Guest - Live"},
            {**source, "track": "Example (Remix)"},
            {**source, "duration": 200},
        ):
            with self.subTest(changed=changed):
                assert playlist_sorter._rank_recordings([changed], metadata) == []
        literal = {**metadata, "title": "Lyrics of Love"}
        literal_source = {**source, "track": "Lyrics of Love", "title": "Artist - Lyrics of Love (Official Audio)"}
        assert (
            playlist_sorter._select_recording(playlist_sorter._rank_recordings([literal_source], literal)) is not None
        )
        assert playlist_sorter._rank_recordings([{**literal_source, "track": "Of Love"}], literal) == []
        # A genuine word in the structured title must not be stripped as an artist prefix.
        named = {"id": "a", "title": "Talk Talk", "artists": ["Talk Talk"], "duration_ms": 180000}
        assert (
            playlist_sorter._select_recording(
                playlist_sorter._rank_recordings(
                    [{**SOURCE, "title": "Talk Talk - Talk Talk", "track": "Talk Talk", "artist": "Talk Talk"}], named
                )
            )
            is not None
        )

    def test_source_access_failures_stop_the_queue_without_uncertain_labels(self) -> None:
        """Do not spend another request on every song after shared sign-in/rate-limit failure."""
        tracks = [{**TRACK, "id": str(index)} for index in range(20)]
        for message, reason in (("Sign in to confirm you're not a bot", "sign_in"), ("HTTP Error 429", "rate_limit")):
            with (
                self.subTest(reason=reason),
                tempfile.TemporaryDirectory() as directory,
                patch.object(playlist_sorter, "_CACHE_FILE", Path(directory) / "cache.json"),
                patch.object(
                    yt_dlp.YoutubeDL, "extract_info", side_effect=yt_dlp.utils.DownloadError(message)
                ) as extract,
            ):
                sorter = playlist_sorter.SpotifyPlaylistSorter("playlist", Mock())
                sorter.youtube_cookies = ""
                result = sorter._fetch_audio_features_local(tracks)
                assert all(item["status"] == "error" and item["reason"] == reason for item in result.values())
                assert extract.call_count <= 2

    def test_real_download_processing_reuses_full_extraction(self) -> None:
        """The installed downloader processes existing formats without another watch request."""
        info = {
            **SOURCE,
            "formats": [
                {
                    "format_id": "test",
                    "url": "https://example.com/audio.m4a",
                    "ext": "m4a",
                    "vcodec": "none",
                    "acodec": "aac",
                }
            ],
        }

        def process(ydl: yt_dlp.YoutubeDL, _info: dict[str, Any]) -> None:
            Path(ydl.params["outtmpl"]["default"] % {"ext": "wav"}).touch()

        with (
            patch.object(
                yt_dlp.YoutubeDL, "extract_info", side_effect=AssertionError("Unexpected extraction")
            ) as extract,
            patch.object(yt_dlp.YoutubeDL, "process_info", autospec=True, side_effect=process) as download,
            patch.object(playlist_sorter, "load_audio", return_value=(np.zeros(180), 1)),
        ):
            assert (
                playlist_sorter.SpotifyPlaylistSorter._download_and_load(
                    {**SOURCE, "url": "https://www.youtube.com/watch?v=abcdefghijk"}, video_info=info
                )[1]
                == 1
            )
            extract.assert_not_called()
            download.assert_called_once()

    def test_expired_download_is_retried_with_fresh_audio_metadata(self) -> None:
        """A 403 must refresh the video extraction rather than repeat the expired media URL."""
        source = {**SOURCE, "url": "https://www.youtube.com/watch?v=abcdefghijk"}
        info = {**SOURCE, "formats": []}
        calls = []

        def process(ydl: yt_dlp.YoutubeDL, video: dict[str, Any], *, download: bool) -> dict[str, Any]:
            assert download
            assert ydl.params["format"] == "bestaudio"
            calls.append(video)
            if len(calls) == 1:
                message = "HTTP Error 403: Forbidden"
                raise yt_dlp.utils.DownloadError(message)
            Path(ydl.params["outtmpl"]["default"] % {"ext": "wav"}).touch()
            return video

        with (
            patch.object(yt_dlp.YoutubeDL, "process_ie_result", autospec=True, side_effect=process),
            patch.object(yt_dlp.YoutubeDL, "extract_info", return_value={**info, "fresh": True}) as extract,
            patch.object(playlist_sorter, "load_audio", return_value=(np.zeros(180), 1)),
            patch.object(playlist_sorter, "sleep"),
        ):
            assert playlist_sorter.SpotifyPlaylistSorter._download_and_load(source, video_info=info)[1] == 1
            extract.assert_called_once_with(source["url"], download=False)
            assert calls[-1]["fresh"]
