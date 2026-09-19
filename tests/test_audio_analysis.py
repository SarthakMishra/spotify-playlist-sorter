"""Generated-audio regression checks; no recordings or network are required."""

# ruff: noqa: INP001, SLF001, PT027
# This repository uses unittest, including its exception assertions.

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, override
from unittest.mock import Mock, patch

import numpy as np
import soundfile as sf
import yt_dlp

from api import audio_analysis, playlist_sorter, recording_match, store
from api.analysis_store import RecordingAnalysis, SectionMeasurements


def recording(track: dict[str, Any], **_kwargs: object) -> dict[str, Any]:
    """Build a complete cache record through the real producer with invented source metadata."""
    source = {"id": "abcdefghijk", "title": track["Track"], "duration": 180.0}
    level = -20.0 if track["id"] == "a" else -10.0
    section = SectionMeasurements(
        start=0.0,
        end=20.0,
        rms_db=level,
        onset=1.0,
        tempo=None,
        tempo_candidates=[],
        centroid=None,
        contrast=None,
        chroma=None,
        camelot=None,
        evidence=dict.fromkeys(("rms_db", "onset", "tempo", "centroid", "contrast", "chroma", "key"), 1.0),
    )
    analysis = RecordingAnalysis(duration=180.0, summary=section, intro=section, body=None, outro=section)
    return recording_match.record_for(source, recording_match._metadata(track), analysis.model_dump())


def stub_analysis(rms_db: float | None = None) -> dict[str, Any]:
    """Make a valid minimal analysis so patched measurements still pass the record seam."""
    section: dict[str, Any] = {
        "start": 0.0,
        "end": 0.0,
        "rms_db": rms_db,
        "onset": None,
        "tempo": None,
        "tempo_candidates": [],
        "centroid": None,
        "contrast": None,
        "chroma": None,
        "camelot": None,
        "evidence": {},
    }
    return {"duration": 0.0, "summary": section, "intro": section, "body": None, "outro": section}


def full_sections(wave: np.ndarray, sr: int = audio_analysis.SAMPLE_RATE) -> list[tuple[str, float, float, np.ndarray]]:
    """Wrap a waveform in the sections a recording download would produce."""
    return [
        (*plan, wave)
        for label, start, end in audio_analysis.section_plan(len(wave) / sr)
        for plan in [(label, start, end)]
    ]


class AudioAnalysisTest(unittest.TestCase):
    """Check measured audio values rather than merely successful extraction."""

    @override
    def setUp(self) -> None:
        """Keep the analysis cache in a temporary database for every test."""
        store.configure(Path(self.enterContext(tempfile.TemporaryDirectory())) / "store.db")

    @override
    def tearDown(self) -> None:
        store.close()

    def test_pitch_classes_and_resampling_amplitude(self) -> None:
        """A is pitch class nine and resampling preserves level after truncation."""
        with self.subTest(signal="440 Hz"):
            sr = 22050
            tone = np.sin(2 * np.pi * 440 * np.arange(sr * 2) / sr).astype(np.float32)
            analysis = audio_analysis.analyze_sections(full_sections(tone), sr)
            assert int(np.argmax(analysis["intro"]["chroma"])) == 9
            assert analysis["summary"]["camelot"] is None
        with tempfile.TemporaryDirectory() as directory, self.subTest(signal="constant level"):
            path = Path(directory) / "generated.wav"
            sf.write(path, np.full(44100 * 60, 0.25, dtype=np.float32), 44100, subtype="FLOAT")
            audio, sr = audio_analysis.load_audio(str(path), duration=30)
            assert sr == 22050
            assert abs(float(np.sqrt(np.mean(audio**2))) - 0.25) < 0.001

    def test_boundaries_short_audio_and_silence(self) -> None:
        """Retain distinct real endings, and withhold unsupported rhythm and key labels."""
        sr = audio_analysis.SAMPLE_RATE
        phases = [(15, 220, 0.05), (10, 440, 0.1), (15, 880, 0.3)]
        wave = np.concatenate(
            [amplitude * np.sin(2 * np.pi * hz * np.arange(seconds * sr) / sr) for seconds, hz, amplitude in phases]
        ).astype(np.float32)
        result = audio_analysis.analyze_sections(full_sections(wave))
        assert result["duration"] == 40
        assert (result["intro"]["start"], result["intro"]["end"]) == (0, 15)
        assert (result["body"]["start"], result["body"]["end"]) == (15, 25)
        assert (result["outro"]["start"], result["outro"]["end"]) == (25, 40)
        assert result["outro"]["rms_db"] - result["intro"]["rms_db"] > 15
        assert result["outro"]["centroid"] > result["intro"]["centroid"] * 3
        for length in (100, sr):
            with self.subTest(samples=length):
                silent = audio_analysis.analyze_sections(full_sections(np.zeros(length, dtype=np.float32)))
                assert silent["summary"]["tempo"] is None
                assert silent["summary"]["camelot"] is None
                assert silent["summary"]["chroma"] is None
                assert silent["summary"]["evidence"]["tempo"] == 0
                assert silent["summary"]["evidence"]["rms_db"] > 0
                assert silent["body"] is None
                assert silent["outro"]["end"] == length / sr
                json.dumps(silent, allow_nan=False)
        with self.assertRaises(ValueError):
            audio_analysis.analyze_sections([("full", 0.0, 1.0, np.array([np.nan], dtype=np.float32))])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "long.wav"
            with sf.SoundFile(path, mode="w", samplerate=sr, channels=1, subtype="PCM_16") as output:
                output.seek(audio_analysis.MAX_SECONDS * sr)
                output.write(np.zeros(1))
            with self.assertRaises(ValueError):
                audio_analysis.load_audio(str(path))

    def test_periodic_audio_retains_tempo_alternatives(self) -> None:
        """A metronome supplies rhythm evidence while half-tempo interpretations remain visible."""
        sr = audio_analysis.SAMPLE_RATE
        wave = np.zeros(15 * sr, dtype=np.float32)
        samples = np.arange(1000)
        click = np.exp(-samples / 150) * np.sin(2 * np.pi * 900 * samples / sr)
        for start in range(0, len(wave) - len(click), sr // 2):
            wave[start : start + len(click)] += click
        summary = audio_analysis.analyze_sections(full_sections(wave))["summary"]
        assert abs(summary["tempo"] - 120) < 3
        assert any(abs(candidate["bpm"] - 60) < 3 for candidate in summary["tempo_candidates"])
        assert 0 < summary["evidence"]["tempo"] < 0.8
        noise = np.random.default_rng(7).normal(0, 0.1, sr * 15).astype(np.float32)
        assert audio_analysis.analyze_sections(full_sections(noise))["summary"]["tempo"] is None

    def test_sampled_sections_cover_boundaries_and_merge(self) -> None:
        """Long tracks download three windows; the merge keeps energy weighting and honest evidence."""
        sr = audio_analysis.SAMPLE_RATE
        assert audio_analysis.section_plan(60.0) == [("full", 0.0, 60.0)]
        plan = audio_analysis.section_plan(240.0)
        assert [(label, round(start, 3), round(end, 3)) for label, start, end in plan] == [
            ("intro", 0.0, 20.0),
            ("body", 110.0, 130.0),
            ("outro", 220.0, 240.0),
        ]
        quiet = (0.02 * np.sin(2 * np.pi * 220 * np.arange(20 * sr) / sr)).astype(np.float32)
        loud = (0.4 * np.sin(2 * np.pi * 440 * np.arange(20 * sr) / sr)).astype(np.float32)
        merged = audio_analysis.analyze_sections(
            [("intro", 0.0, 20.0, quiet), ("body", 110.0, 130.0, loud), ("outro", 220.0, 240.0, quiet)]
        )
        assert merged["duration"] == 240.0
        assert (merged["intro"]["start"], merged["intro"]["end"]) == (0, 15)
        assert (merged["outro"]["start"], merged["outro"]["end"]) == (5, 20)
        assert merged["body"]["start"] == 0
        quiet_db, loud_db = merged["intro"]["rms_db"], merged["body"]["rms_db"]
        assert quiet_db < merged["summary"]["rms_db"] < loud_db  # two quiet windows outweigh one loud one
        assert merged["summary"]["evidence"]["rms_db"] == 1.0
        assert merged["summary"]["camelot"] is None  # pure tones never name a key
        json.dumps(merged, allow_nan=False)

    def test_merge_reconciles_octave_and_merges_duplicate_peaks(self) -> None:
        """The summary beat follows the windows' half/double decisions, not the strongest raw peak."""

        def window(tempo: float | None, candidates: list[dict[str, float]]) -> dict[str, Any]:
            return {
                "start": 0.0,
                "end": 20.0,
                "rms_db": -10.0,
                "onset": 1.0,
                "tempo": tempo,
                "tempo_candidates": candidates,
                "centroid": None,
                "contrast": None,
                "chroma": None,
                "camelot": None,
                "evidence": dict.fromkeys(("rms_db", "onset", "tempo", "centroid", "contrast", "chroma", "key"), 0.8),
            }

        # Sparse sections raise a stronger half-tempo peak, but each window's estimate chose 140.
        parts = [
            window(140.0, [{"bpm": 70.0, "strength": 0.8}, {"bpm": 140.0, "strength": 0.62}]),
            window(140.0, [{"bpm": 70.0, "strength": 0.72}, {"bpm": 140.0, "strength": 0.58}]),
        ]
        merged = audio_analysis._merge_windows(parts)
        assert merged["tempo"] == 140.0
        assert abs(merged["tempo_candidates"][0]["bpm"] - 70.0) < 1.0
        assert 0 < merged["evidence"]["tempo"] <= 0.8

        split = [window(120.0, [{"bpm": 119.96, "strength": 0.6}]), window(120.0, [{"bpm": 120.04, "strength": 0.6}])]
        merged = audio_analysis._merge_windows(split)
        assert abs(merged["tempo"] - 120.0) < 0.1
        assert len(merged["tempo_candidates"]) == 1  # near-identical estimates merge instead of splitting

        unchosen = [window(None, [{"bpm": 90.0, "strength": 0.5}]), window(None, [])]
        merged = audio_analysis._merge_windows(unchosen)
        assert merged["tempo"] == 90.0  # falls back to the strongest candidate without window choices

    def test_recording_match_rejects_wrong_sources_and_accepts_best_effort_ties(self) -> None:
        """Single results and popular wrong versions face the same eligibility rules."""
        metadata = {"id": "a", "title": "Example", "artists": ["Artist"], "duration_ms": 180000}
        source = {
            "id": "abcdefghijk",
            "title": "Artist - Example (Official Audio)",
            "duration": 180,
            "artist": "Artist",
        }
        ranked = recording_match._rank_recordings([source], metadata)
        selected = recording_match._select_recording(ranked)
        assert selected is not None
        assert selected["id"] == source["id"]
        variants = ["Live", "Remix", "Radio edit", "Extended", "Karaoke", "Instrumental", "Cover", "Acoustic"]
        invalid: list[dict[str, Any]] = [
            {**source, "title": f"Artist - Example ({variant})", "view_count": 1000000} for variant in variants
        ]
        invalid.extend(
            [
                {**source, "title": "Artist - Wrong song"},
                {**source, "duration": None},
                {**source, "duration": 210},
                {**source, "title": "Example", "artist": "Someone else"},
            ]
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate):
                assert (
                    recording_match._select_recording(recording_match._rank_recordings([candidate], metadata)) is None
                )
        for missing in ({**metadata, "artists": []}, {**metadata, "duration_ms": None}):
            assert recording_match._rank_recordings([source], missing) == []
        assert (
            recording_match._select_recording(
                recording_match._rank_recordings(
                    [source, {**source, "id": "lmnopqrstuv", "view_count": 1000000}],
                    metadata,
                )
            )
            is not None
        )
        remaster = {**metadata, "title": "Example (Remastered 2011)"}
        candidate = {**source, "title": "Artist - Example (Remastered 2011)"}
        assert recording_match._select_recording(recording_match._rank_recordings([candidate], remaster)) is not None
        candidate["title"] = "Artist - Example (Remastered 2012)"
        assert recording_match._rank_recordings([candidate], remaster) == []
        assert (
            recording_match._select_recording(
                recording_match._rank_recordings(
                    [{**source, "title": "Live - Example", "artist": "Live"}],
                    {**metadata, "artists": ["Live"]},
                )
            )
            is not None
        )

    def test_download_fallback_rechecks_eligibility(self) -> None:
        """Try another eligible candidate after a failure, including when candidates tie."""
        track = {"id": "a", "Track": "Example", "Artist": "Artist", "duration_ms": 180000}
        source = {"id": "abcdefghijk", "title": "Artist - Example", "duration": 180}
        fallback = {**source, "id": "lmnopqrstuv", "duration": 182}
        sections = [("full", 0.0, 180.0, np.zeros(1))]
        with (
            patch.object(yt_dlp.YoutubeDL, "extract_info", return_value={"entries": [source, fallback]}) as search,
            patch.object(
                recording_match,
                "_download_sections",
                side_effect=[OSError("Download failed"), sections],
            ) as download,
            patch.object(recording_match, "analyze_sections", return_value=stub_analysis()),
        ):
            search.side_effect = lambda url, **_: (
                search.return_value
                if url.startswith("ytsearch")
                else next(entry for entry in search.return_value["entries"] if url.endswith(entry["id"]))
            )
            result = recording_match.analyze_track(track)
            assert result["status"] == "ready"
            assert result["source"]["id"] == fallback["id"]
            assert download.call_count == 2
            download.reset_mock()
            search.return_value = {"entries": [source, {**fallback, "duration": 180}]}
            download.side_effect = None
            download.return_value = sections
            assert recording_match.analyze_track(track)["status"] == "ready"
            download.assert_called_once()
            search.reset_mock()
            assert recording_match.analyze_track({**track, "duration_ms": 1201000})["status"] == "unsupported"
            search.assert_not_called()

    def test_cache_reuse_invalidation_and_raw_measurements(self) -> None:
        """Cache a recording once, preserve raw values, and reject stale input/source versions."""
        tracks = [{"id": key, "Track": "Example", "Artist": "Artist", "duration_ms": 180000} for key in ("a", "b", "a")]
        assert playlist_sorter._load_cache() == {}
        sorter = playlist_sorter.SpotifyPlaylistSorter("playlist", Mock())
        progress = Mock()
        with patch.object(playlist_sorter, "analyze_track", side_effect=recording) as analyze:
            first = sorter._fetch_audio_features_local(tracks, progress)
            assert analyze.call_count == 2
            assert sorter.recording_count == 2
            assert sorter.cached_count == 0
            assert progress.call_args.args == (3, 3)
            raw = copy.deepcopy(playlist_sorter._load_cache())
            assert "energy" not in raw["a"]
            analyze.reset_mock()
            assert sorter._fetch_audio_features_local(tracks) == first
            assert sorter.cached_count == 3
            analyze.assert_not_called()
            assert playlist_sorter._load_cache() == raw
            unknown_activity = copy.deepcopy(raw)
            unknown_activity["a"]["analysis"]["summary"]["onset"] = None
            unknown_activity["b"]["analysis"]["summary"]["onset"] = 4.0
            assert playlist_sorter._with_intensity(unknown_activity)["a"]["energy"] == 0.2
            unmeasured = copy.deepcopy(raw)
            unmeasured["a"]["analysis"]["summary"]["evidence"]["rms_db"] = 0.0
            unmeasured["a"]["analysis"]["summary"]["evidence"]["onset"] = 0.0
            assert playlist_sorter._with_intensity(unmeasured)["a"]["energy"] == 0.5
            changed = [{**track, "Track": "Changed"} if track["id"] == "a" else track for track in tracks]
            sorter._fetch_audio_features_local(changed)
            assert analyze.call_count == 1
            analyze.reset_mock()
            changed_record = json.loads(store.cache_records()["a"])
            changed_record["source"]["id"] = "changed-id1"
            store.save_cache_records({"a": json.dumps(changed_record)})
            sorter._fetch_audio_features_local(changed)
            assert analyze.call_count == 1
            analyze.reset_mock()
            store.reset_cache({"analysis_version": "old-version"}, {})
            sorter._fetch_audio_features_local(changed)
            assert analyze.call_count == 2

    def test_cache_checkpoints_keep_the_prior_records_on_failure(self) -> None:
        """Keep completed analyses on interruption and the prior cache on a write failure."""
        tracks = [{"id": str(i), "Track": "Example", "Artist": "Artist", "duration_ms": 180000} for i in range(11)]
        sorter = playlist_sorter.SpotifyPlaylistSorter("playlist", Mock())

        def interrupt(done: int, total: int) -> None:
            if done == total:
                raise InterruptedError

        with (
            patch.object(playlist_sorter, "analyze_track", side_effect=recording),
            patch.object(playlist_sorter, "_save_cache", wraps=playlist_sorter._save_cache) as save,
            self.assertRaises(InterruptedError),
        ):
            sorter._fetch_audio_features_local(tracks, interrupt)
        assert save.call_count == 2
        assert len(playlist_sorter._load_cache()) == 11
        previous = playlist_sorter._load_cache()
        with (
            patch.object(store, "save_cache_records", side_effect=OSError("Disk failure")),
            self.assertRaises(OSError),
        ):
            playlist_sorter._save_cache({})
        assert playlist_sorter._load_cache() == previous
