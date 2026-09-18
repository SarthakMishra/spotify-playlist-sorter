"""Recording-resolution regressions with invented metadata and no external requests."""

# ruff: noqa: INP001, SLF001

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from threading import Barrier, Event, Thread
from time import sleep
from typing import Any
from unittest.mock import Mock, patch

import numpy as np
import yt_dlp

from api import playlist_sorter

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
            patch.object(
                playlist_sorter.SpotifyPlaylistSorter,
                "_download_sections",
                return_value=[("full", 0.0, 180.0, np.zeros(1))],
            ),
            patch.object(playlist_sorter, "analyze_sections", return_value={"summary": {}}),
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
            patch.object(
                playlist_sorter.SpotifyPlaylistSorter,
                "_download_sections",
                return_value=[("full", 0.0, 180.0, np.zeros(1))],
            ) as download,
            patch.object(playlist_sorter, "analyze_sections", return_value={"summary": {}}),
        ):
            result = playlist_sorter.SpotifyPlaylistSorter._analyze_track(TRACK, cookie_text="")
            assert result["status"] == "ready", result
            assert len(hydrated) <= 3, f"Hydrated {len(hydrated)} candidates for one recording"
            assert download.call_count == 1

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

    def test_channel_evidence_rescues_credit_spelling_and_unattributed_uploads(self) -> None:
        """Live-observed uploads: misspelled credits, absent credits and decorated titles still match."""
        # Kanha Unplugged: YouTube credits misspell the artist; the official channel supplies evidence.
        kanha = {
            "id": "abcdefghijk",
            "title": 'Kanha Unplugged (From "Shubh Mangal Saavdhan")',
            "track": 'Kanha Unplugged (From "Shubh Mangal Saavdhan")',
            "artists": ["Ayushman Khurrana"],
            "duration": 176,
            "channel": "Ayushmann Khurrana",
        }
        kanha_meta = {
            "id": "a",
            "title": "Kanha Unplugged",
            "artists": ["Tanishk-Vayu", "Ayushmann Khurrana"],
            "duration_ms": 176000,
        }
        assert playlist_sorter._select_recording(playlist_sorter._rank_recordings([kanha], kanha_meta)) is not None
        # Saudebazi (Encore): exact title and duration with no credits and no verification.
        encore = {"id": "abcdefghijk", "title": "SAUDEBAZI (ENCORE)", "duration": 354}
        encore_meta = {
            "id": "b",
            "title": "Saudebazi (Encore)",
            "artists": ["Pritam", "Javed Ali"],
            "duration_ms": 354000,
        }
        assert playlist_sorter._select_recording(playlist_sorter._rank_recordings([encore], encore_meta)) is not None
        # In Dino Refresh: word recall finds the requested title inside a decorated upload title.
        refresh = {
            "id": "abcdefghijk",
            "title": "In Dino - Mohammed Irfan | Sony Music Refresh | Ajay Singha",
            "duration": 254,
            "channel": "Sony Music India",
        }
        refresh_meta = {
            "id": "c",
            "title": "In Dino - Refresh Version",
            "artists": ["Mohammed Irfan"],
            "duration_ms": 256000,
        }
        assert playlist_sorter._select_recording(playlist_sorter._rank_recordings([refresh], refresh_meta)) is not None
        # Mera Pehla Pehla Pyaar: K.K. versus KK is the same artist; adjacent tokens squeeze to one.
        initials = {
            "id": "abcdefghijk",
            "title": "Mera Pehla Pehla Pyaar",
            "track": "Mera Pehla Pehla Pyaar",
            "artists": ["K.K.", "Vipin Mishra"],
            "duration": 271,
            "channel": "Kay Kay - Topic",
        }
        initials_meta = {"id": "d", "title": "Mera Pehla Pehla Pyaar", "artists": ["KK"], "duration_ms": 271025}
        assert (
            playlist_sorter._select_recording(playlist_sorter._rank_recordings([initials], initials_meta)) is not None
        )
        # A labeled cover conflicts on the edition tag regardless of everything else.
        cover = {"id": "abcdefghijk", "title": "Example (Cover)", "duration": 180, "channel": "Random Covers"}
        cover_meta = {"id": "e", "title": "Example", "artists": ["Artist"], "duration_ms": 180000}
        assert playlist_sorter._rank_recordings([cover], cover_meta) == []

    def test_requested_edition_words_are_required_evidence(self) -> None:
        """When the requested title declares an edition, uploads that omit it are different recordings."""
        # Trailing parenthetical: the default upload must not stand in for the reprise.
        reprise_meta = {
            "id": "a",
            "title": "Zindagi Kuch Toh Bata (Reprise)",
            "artists": ["Jubin Nautiyal"],
            "duration_ms": 258000,
        }
        original = {
            "id": "abcdefghijk",
            "title": "Zindagi Kuch Toh Bata",
            "track": "Zindagi Kuch Toh Bata",
            "artists": ["Rahat Fateh Ali Khan"],
            "duration": 262,
            "channel": "Pritam",
            "channel_is_verified": True,
        }
        assert playlist_sorter._rank_recordings([original], reprise_meta) == []
        labeled = {
            **original,
            "track": "Zindagi Kuch Toh Bata (Reprise)",
            "artists": ["Jubin Nautiyal"],
            "title": "Zindagi Kuch Toh Bata (Reprise)",
        }
        assert playlist_sorter._rank_recordings([labeled], reprise_meta) != []
        # Trailing dash groups count too, and the qualifier may appear anywhere in the upload text.
        refresh_meta = {
            "id": "b",
            "title": "In Dino - Refresh Version",
            "artists": ["Mohammed Irfan"],
            "duration_ms": 256000,
        }
        decorated = {
            "id": "abcdefghijk",
            "title": "In Dino - Mohammed Irfan | Sony Music Refresh | Ajay Singha",
            "duration": 254,
            "channel": "Sony Music India",
        }
        assert (
            playlist_sorter._select_recording(playlist_sorter._rank_recordings([decorated], refresh_meta)) is not None
        )
        unlabeled = {**decorated, "id": "lmnopqrstuv", "title": "In Dino - Mohammed Irfan | Ajay Singha"}
        ranked = playlist_sorter._rank_recordings([decorated, unlabeled], refresh_meta)
        assert ranked, "edition evidence must rank the decorated upload"
        assert ranked[0]["id"] == decorated["id"]  # edition evidence outranks the unlabeled copy
        assert ranked[1]["score"] < ranked[0]["score"]
        # From-movie groups never act as version requirements.
        from_meta = {
            "id": "c",
            "title": 'Dil Cheez Tujhe Dedi (From "Airlift")',
            "artists": ["Arijit Singh"],
            "duration_ms": 300000,
        }
        plain = {"id": "abcdefghijk", "title": "Dil Cheez Tujhe Dedi", "duration": 300, "artist": "Arijit Singh"}
        assert playlist_sorter._rank_recordings([plain], from_meta) != []

    def test_edition_omissions_accept_unlabeled_official_uploads(self) -> None:
        """Unlabeled default uploads satisfy edition requests unless credits name another singer."""
        cases = [
            (
                {
                    "id": "a",
                    "title": "Te Amo (Duet)",
                    "artists": ["Pritam", "Ash King", "Sunidhi Chauhan"],
                    "duration_ms": 284723,
                },
                {
                    "id": "abcdefghijk",
                    "title": "Te Amo",
                    "track": "Te Amo",
                    "artists": ["Pritam"],
                    "duration": 284,
                    "channel": "Pritam",
                    "channel_is_verified": True,
                },
            ),
            (
                {
                    "id": "b",
                    "title": "Pani Da Rang - Male",
                    "artists": ["Ayushmann Khurrana", "Rochak Kohli"],
                    "duration_ms": 240786,
                },
                {
                    "id": "abcdefghijk",
                    "title": "Pani Da Rang - Lyrical Video | Vicky Donor | Ayushmann Khurrana | Yami Gautam",
                    "duration": 238,
                    "channel": "Sony Music India",
                    "channel_is_verified": True,
                },
            ),
            (
                {
                    "id": "c",
                    "title": "Har Kisi Ko (Female)",
                    "artists": ["Arijit Singh", "Neeti Mohan", "Chirantan Bhatt"],
                    "duration_ms": 337046,
                },
                {
                    "id": "abcdefghijk",
                    "title": "Arijit Singh, Neeti Mohan - Har Kisi Ko (Lyrics)",
                    "duration": 338,
                    "channel": "D-Muze India",
                },
            ),
            (
                {
                    "id": "d",
                    "title": "Yaariyaan - Male",
                    "artists": ["Pritam", "Mohan Kannan", "Shilpa Rao"],
                    "duration_ms": 374173,
                },
                {
                    "id": "abcdefghijk",
                    "title": "Yaariyaan (Lyrics) - Cocktail | Mohan Kanan, Shilpa Rao",
                    "duration": 375,
                    "channel": "Geet Mantra",
                },
            ),
        ]
        for metadata, upload in cases:
            with self.subTest(title=metadata["title"]):
                assert (
                    playlist_sorter._select_recording(playlist_sorter._rank_recordings([upload], metadata)) is not None
                )
        # The default upload of a different singer stays rejected even without its edition label.
        reprise_meta = {
            "id": "e",
            "title": "Zindagi Kuch Toh Bata (Reprise)",
            "artists": ["Pritam", "Jubin Nautiyal", "Neelesh Misra"],
            "duration_ms": 258877,
        }
        original = {
            "id": "abcdefghijk",
            "title": "Zindagi Kuch Toh Bata",
            "track": "Zindagi Kuch Toh Bata",
            "artists": ["Pritam", "Rahat Fateh Ali Khan", "Rekha Bhardwaj", "Neelesh Misra"],
            "duration": 263,
            "channel": "Pritam",
            "channel_is_verified": True,
        }
        assert playlist_sorter._rank_recordings([original], reprise_meta) == []
        # An upload claiming an edition the request never asked for stays rejected.
        claimed = {
            "id": "abcdefghijk",
            "title": "Lagan Laagi Re (Reprise)",
            "track": "Lagan Laagi Re (Reprise)",
            "artists": ["Amit Trivedi"],
            "duration": 279,
            "channel": "Amit Trivedi",
        }
        plain_meta = {
            "id": "f",
            "title": "Lagan Laagi Re",
            "artists": ["Amit Trivedi", "Shreya Ghoshal"],
            "duration_ms": 278653,
        }
        assert playlist_sorter._rank_recordings([claimed], plain_meta) == []

    def test_fuzzy_token_recall_tolerates_spelling_variants(self) -> None:
        """Saathiyaa/Sathiya-class spelling differences no longer hide the right upload."""
        metadata = {"id": "a", "title": "Saathiyaa", "artists": ["Shreya Ghoshal", "Ajay"], "duration_ms": 310924}
        upload = {
            "id": "abcdefghijk",
            "title": "Sathiya Lyrics | Shreya Ghoshal | Ajay- Atul | Kajal Agarwal",
            "duration": 310,
            "channel": "RB Lyrics Lover",
        }
        assert playlist_sorter._shortlist([upload], metadata)
        selected = playlist_sorter._select_recording(playlist_sorter._rank_recordings([upload], metadata))
        assert selected is not None

    def test_flat_search_retry_drops_failed_hints(self) -> None:
        """When the audio-hinted query returns junk, the plain query still finds the official upload."""
        official = {
            "id": "abcdefghijk",
            "title": "Dil Darbadar",
            "duration": 378,
            "channel": "Ankit Tiwari",
        }
        queries = []

        def extract(_ydl: yt_dlp.YoutubeDL, url: str, **_kwargs: object) -> dict[str, Any]:
            queries.append(url)
            if url.startswith("ytsearch"):
                if "audio" in url:
                    return {
                        "entries": [{"id": "junkid0x", "title": "Dil Darbadar Ankit Tiwari audio", "duration": None}]
                    }
                return {"entries": [official]}
            return official

        with patch.object(yt_dlp.YoutubeDL, "extract_info", autospec=True, side_effect=extract):
            ranked, _full, _candidates = playlist_sorter.SpotifyPlaylistSorter._find_recordings(
                {"id": "a", "title": "Dil Darbadar", "artists": ["Ankit Tiwari"], "duration_ms": 377045}, "", {}
            )
        searches = [query for query in queries if query.startswith("ytsearch")]
        assert len(searches) == 2, f"expected exactly two searches, got {searches}"
        assert "audio" in searches[0]
        assert "audio" not in searches[1]
        assert playlist_sorter._select_recording(ranked) is not None

    def test_fallback_shortlist_hydrates_other_script_titles(self) -> None:
        """Duration-compatible uploads in other scripts hydrate and reveal plain English names."""
        metadata = {
            "id": "a",
            "title": "Zindagi Kuch Toh Bata (Reprise)",
            "artists": ["Pritam", "Jubin Nautiyal"],
            "duration_ms": 258877,
        }
        hindi = {"id": "abcdefghijk", "title": "ज़िन्दगी कुछ तो बता (रिप्राइज) पूरा ऑडियो गाना", "duration": 259}
        english = {"id": "lmnopqrstuv", "title": "Wrong song entirely", "duration": 259}

        def extract(_ydl: yt_dlp.YoutubeDL, url: str, **_kwargs: object) -> dict[str, Any]:
            if url.startswith("ytsearch"):
                return {"entries": [hindi, english]}
            return hindi if url.endswith(str(hindi["id"])) else english

        def hydrated_extract(ydl: yt_dlp.YoutubeDL, url: str, **_kwargs: object) -> dict[str, Any]:
            if url.startswith("ytsearch"):
                return extract(ydl, url)
            video = dict(hindi if url.endswith(str(hindi["id"])) else english)
            if video is hindi:
                video["title"] = "Zindagi Kuch Toh Bata (Reprise) Full AUDIO Song Pritam"
            return video

        with patch.object(yt_dlp.YoutubeDL, "extract_info", autospec=True, side_effect=hydrated_extract):
            candidates = playlist_sorter._shortlist([hindi, english], metadata)
            assert [c["id"] for c in candidates] == [hindi["id"], english["id"]]  # both survive the shortlist

    def test_retry_sleep_functions_accept_keyword_counts(self) -> None:
        """yt-dlp calls retry sleep helpers with a keyword; a TypeError would crash every retry."""
        functions = playlist_sorter.youtube_options("")["retry_sleep_functions"]
        for key in ("http", "fragment", "extractor"):
            with self.subTest(key=key):
                assert functions[key](n=2) == 4

    def test_worker_scale_limits_growth_by_machine_and_bandwidth(self) -> None:
        """Start conservatively, grow after fast successes to the machine cap, and back off on rate limits."""
        with patch.object(playlist_sorter._WorkerScale, "_machine_limit", return_value=4):
            scale = playlist_sorter._WorkerScale()
        assert scale.target == 2  # conservative start regardless of capacity
        fast = {"status": "ready", "diagnostics": {"download_seconds": 2.0}}
        for _ in range(8):
            scale.adjust(fast)
        assert scale.target == 3
        for _ in range(8):
            scale.adjust(fast)
        assert scale.target == 4  # machine cap reached and held
        for _ in range(8):
            scale.adjust(fast)
        assert scale.target == 4
        scale.adjust({"status": "ready", "diagnostics": {"download_seconds": 30.0}})
        assert scale.target == 4  # already at cap; slow downloads matter below it
        scale.adjust({"status": "error", "reason": "rate_limit"})
        assert scale.target == 1
        with patch.object(playlist_sorter._WorkerScale, "_machine_limit", return_value=2):
            scale = playlist_sorter._WorkerScale()
        assert scale.target == 2
        for _ in range(16):
            scale.adjust(fast)
        assert scale.target == 2  # machine cap
        with patch.object(playlist_sorter._WorkerScale, "_machine_limit", return_value=4):
            scale = playlist_sorter._WorkerScale()
        for _ in range(8):
            scale.adjust(fast)
        assert scale.target == 3
        scale.adjust({"status": "ready", "diagnostics": {"download_seconds": 30.0}})
        assert scale.target == 3  # slow download blocks growth

    def test_dynamic_gate_tracks_target_changes(self) -> None:
        """Only the target's worth of workers proceed; the rest wait for a slot."""
        gate = playlist_sorter._DynamicGate(1)
        entered = []
        release = Event()

        def worker() -> None:
            with gate:
                entered.append(1)
                release.wait(2)

        threads = [Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        sleep(0.2)
        assert entered == [1]  # a second worker cannot pass a target of one
        release.set()
        for thread in threads:
            thread.join(2)
        assert entered == [1, 1]

    def test_shared_video_measurements_are_reused_within_a_job(self) -> None:
        """Two Spotify entries resolving to one upload download and decode only once."""
        track = {"id": "a", "Track": "Example", "Artist": "Artist", "duration_ms": 180000}
        video = {**SOURCE, "title": "Artist - Example", "artist": "Artist"}

        def extract(_ydl: yt_dlp.YoutubeDL, url: str, **_kwargs: object) -> dict[str, Any]:
            return {"entries": [video]} if url.startswith("ytsearch") else video

        reused_analysis = {"summary": {"rms_db": -12.0}}
        with (
            patch.object(yt_dlp.YoutubeDL, "extract_info", autospec=True, side_effect=extract),
            patch.object(
                playlist_sorter.SpotifyPlaylistSorter,
                "_download_sections",
                return_value=[("full", 0.0, 180.0, np.zeros(1))],
            ) as download,
            patch.object(playlist_sorter, "analyze_sections", return_value=reused_analysis),
        ):
            first = playlist_sorter.SpotifyPlaylistSorter._analyze_track(track, cookie_text="", video_analyses={})
            assert first["status"] == "ready"
            assert download.call_count == 1
            second = playlist_sorter.SpotifyPlaylistSorter._analyze_track(
                {**track, "id": "b"}, cookie_text="", video_analyses={str(video["id"]): first}
            )
            assert second["status"] == "ready"
            assert second["analysis"] == reused_analysis
            assert download.call_count == 1
            assert second["source_fingerprint"] == first["source_fingerprint"]

    def test_source_access_failures_stop_the_queue_without_uncertain_labels(self) -> None:
        """Do not spend another request on every song after shared sign-in/rate-limit failure."""
        tracks = [{**TRACK, "id": str(index)} for index in range(20)]
        for message, reason in (("Sign in to confirm you're not a bot", "sign_in"), ("HTTP Error 429", "rate_limit")):
            with (
                self.subTest(reason=reason),
                tempfile.TemporaryDirectory() as directory,
                patch.object(playlist_sorter, "_CACHE_FILE", Path(directory) / "cache.json"),
                patch.object(playlist_sorter._WorkerScale, "_machine_limit", return_value=2),
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
            patch.object(playlist_sorter, "load_audio", return_value=(np.zeros(20 * 22050), 22050)),
        ):
            sections = playlist_sorter.SpotifyPlaylistSorter._download_sections(
                {**SOURCE, "url": "https://www.youtube.com/watch?v=abcdefghijk"}, video_info=info
            )
            assert [(label, start, end) for label, start, end, _audio in sections] == [
                ("intro", 0.0, 20.0),
                ("body", 80.0, 100.0),
                ("outro", 160.0, 180.0),
            ]
            extract.assert_not_called()
            assert download.call_count == 3

    def test_sections_download_concurrently_in_plan_order(self) -> None:
        """Overlapping section downloads cut wall time while results stay in plan order."""
        source = {**SOURCE, "url": "https://www.youtube.com/watch?v=abcdefghijk"}
        info = {**SOURCE, "formats": []}
        barrier = Barrier(3)
        marker = {"intro": 1.0, "body": 2.0, "outro": 3.0}

        def section(_video: dict[str, Any], plan_section: tuple[str, float, float], *_args: object) -> np.ndarray:
            barrier.wait(timeout=5)  # a sequential download cannot reach three simultaneous arrivals
            sleep(0.05 if plan_section[0] == "intro" else 0.0)
            return np.full(20 * 22050, marker[plan_section[0]], dtype=np.float32)

        with patch.object(playlist_sorter.SpotifyPlaylistSorter, "_download_section", side_effect=section):
            sections = playlist_sorter.SpotifyPlaylistSorter._download_sections(source, video_info=info)

        assert [(label, start, end) for label, start, end, _audio in sections] == [
            ("intro", 0.0, 20.0),
            ("body", 80.0, 100.0),
            ("outro", 160.0, 180.0),
        ]
        assert [float(sections[index][3][0]) for index in range(3)] == [1.0, 2.0, 3.0]

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
            patch.object(playlist_sorter, "load_audio", return_value=(np.zeros(20 * 22050), 22050)),
            patch.object(playlist_sorter, "sleep"),
        ):
            assert playlist_sorter.SpotifyPlaylistSorter._download_sections(source, video_info=info)
            extract.assert_called_once_with(source["url"], download=False)
            assert calls[-1]["fresh"]
