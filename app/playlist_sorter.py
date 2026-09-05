"""Spotify playlist sorting module for optimal track transitions."""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
import soundfile as sf
import spotipy
import yt_dlp

# Import constants from local constants module
from app.constants import (
    BPM_GOOD_THRESHOLD,
    BPM_MEDIUM_THRESHOLD,
    CAMELOT_MAX_NUMBER,
    CAMELOT_MIN_NUMBER,
    ENERGY_MODERATE_INCREASE_MAX,
    ENERGY_SCALING_FACTOR,
    ENERGY_SMALL_DECREASE_MIN,
    ENERGY_SMALL_INCREASE_MAX,
)

# Mapping from (pitch_class, mode) -> Camelot key
# pitch_class: 0=C, 1=C#, 2=D, ... 11=B  |  mode: 0=minor, 1=major
_CAMELOT_MAP: dict[tuple[int, int], str] = {
    (0, 1): "8B",
    (1, 1): "3B",
    (2, 1): "10B",
    (3, 1): "5B",
    (4, 1): "12B",
    (5, 1): "7B",
    (6, 1): "2B",
    (7, 1): "9B",
    (8, 1): "4B",
    (9, 1): "11B",
    (10, 1): "6B",
    (11, 1): "1B",
    (0, 0): "5A",
    (1, 0): "12A",
    (2, 0): "7A",
    (3, 0): "2A",
    (4, 0): "9A",
    (5, 0): "4A",
    (6, 0): "11A",
    (7, 0): "6A",
    (8, 0): "1A",
    (9, 0): "8A",
    (10, 0): "3A",
    (11, 0): "10A",
}

# Krumhansl-Kessler key profiles (C, C#, D, … B) for key detection
_KK_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KK_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

if TYPE_CHECKING:
    from collections.abc import Callable

# Configure logger
logger = logging.getLogger(__name__)

# Constants for transition analysis
MIN_TRANSITION_COUNT = 2

# Maximum acceptable duration difference (seconds) between Spotify and YouTube tracks.
# Set generously — YouTube versions often have intros/outros that differ slightly.

# Patterns to strip from track names before YouTube search
# Removes: (feat. ...), [Remastered ...], (Deluxe ...), etc.
_TRACK_NOISE_KEYWORDS = {
    "feat",
    "ft",
    "with",
    "prod",
    "remaster",
    "deluxe",
    "bonus",
    "demo",
    "version",
    "edit",
    "radio",
}
_BRACKETED_RE = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]")

# Variant keywords — if present in the YouTube title but NOT in the Spotify track
# (or vice versa), the result is likely the wrong version of the song.
_VARIANT_KEYWORDS = {
    "remix",
    "remixed",
    "slowed",
    "reverb",
    "reverbed",
    "sped up",
    "speed up",
    "bass boosted",
    "8d audio",
    "8d",
    "lofi",
    "lo-fi",
    "lo fi",
    "instrumental",
    "cover",
    "mashup",
    "mash up",
    "live",
    "concert",
    "acoustic",
    "unplugged",
    "radio edit",
    "extended",
    "club mix",
}

# Keywords that indicate a clean audio source — give these a slight boost
_PREFERRED_KEYWORDS = {"lyrics", "lyric", "lyrical", "karaoke", "official audio", "full song", "full video"}

# Default parallel workers — network I/O bound, so more workers help
_DEFAULT_MAX_WORKERS = min(12, (os.cpu_count() or 4) + 4)

# Audio analysis cache — persists results across runs so we skip yt-dlp
# for tracks we've already analyzed.
_CACHE_FILE = Path(__file__).resolve().parent.parent / ".analysis_cache.json"

_TARGET_SR = 22050


def _load_audio(filepath: str, sr: int = _TARGET_SR, duration: float = 30.0) -> tuple[np.ndarray, int]:
    """Load audio file, convert to mono, resample, and truncate."""
    data, orig_sr = sf.read(filepath, dtype="float32", always_2d=True)
    # Mix to mono
    y = data.mean(axis=1)
    # Truncate to duration
    max_samples = int(duration * orig_sr)
    if len(y) > max_samples:
        y = y[:max_samples]
    # Resample using FFT-based method (replaces scipy.signal.resample)
    if orig_sr != sr:
        num_samples = int(len(y) * sr / orig_sr)
        y_freq = np.fft.rfft(y)
        new_freq = np.zeros(num_samples // 2 + 1, dtype=np.complex64)
        n_copy = min(len(y_freq), len(new_freq))
        new_freq[:n_copy] = y_freq[:n_copy]
        y = np.fft.irfft(new_freq, n=num_samples).astype(np.float32)
        y *= num_samples / len(data)
    return y, sr


def _find_peaks(x: np.ndarray) -> np.ndarray:
    """Find local maxima in a 1-D array (replaces scipy.signal.find_peaks)."""
    if len(x) < 3:  # noqa: PLR2004
        return np.array([], dtype=int)
    return np.where((x[1:-1] > x[:-2]) & (x[1:-1] > x[2:]))[0] + 1


def _estimate_tempo(y: np.ndarray, sr: int) -> float:
    """Estimate BPM using onset-strength autocorrelation (similar to librosa)."""
    # Compute a simple spectral flux onset strength envelope
    hop = 512
    n_fft = 2048
    # STFT magnitude
    n_frames = 1 + (len(y) - n_fft) // hop
    if n_frames < 2:  # noqa: PLR2004
        return 120.0  # fallback
    onset_env = np.zeros(n_frames, dtype=np.float32)
    window = np.hanning(n_fft).astype(np.float32)
    for i in range(n_frames):
        frame = y[i * hop : i * hop + n_fft] * window
        mag = np.abs(np.fft.rfft(frame))
        onset_env[i] = mag.sum()
    # Half-wave rectified first-order difference
    onset_env = np.maximum(0, np.diff(onset_env))
    if len(onset_env) < 4:  # noqa: PLR2004
        return 120.0

    # Autocorrelation of onset envelope
    corr = np.correlate(onset_env, onset_env, mode="full")
    corr = corr[len(corr) // 2 :]
    # BPM range: 60-200 -> lag range in frames
    fps = sr / hop
    min_lag = max(1, int(fps * 60 / 200))
    max_lag = min(len(corr) - 1, int(fps * 60 / 60))
    if min_lag >= max_lag:
        return 120.0
    corr_slice = corr[min_lag : max_lag + 1]
    peaks = _find_peaks(corr_slice)
    if len(peaks) == 0:
        best_lag = min_lag + int(np.argmax(corr_slice))
    else:
        best_lag = min_lag + peaks[int(np.argmax(corr_slice[peaks]))]
    return float(60.0 * fps / best_lag)


def _chroma_stft(y: np.ndarray, sr: int, n_fft: int = 4096, hop: int = 512) -> np.ndarray:
    """Compute 12-bin chroma via STFT (lightweight replacement for librosa.feature.chroma_cqt)."""
    n_frames = 1 + (len(y) - n_fft) // hop
    chroma = np.zeros((12, max(n_frames, 1)), dtype=np.float32)
    if n_frames < 1:
        return chroma
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sr)
    # Map each FFT bin to a chroma pitch class (skip DC / very low freqs)
    valid = freqs > 20  # noqa: PLR2004
    pitches = np.round(12 * np.log2(freqs[valid] / 440.0 + 1e-10)) % 12
    pitches = pitches.astype(int)
    window = np.hanning(n_fft).astype(np.float32)
    for i in range(n_frames):
        frame = y[i * hop : i * hop + n_fft] * window
        mag = np.abs(np.fft.rfft(frame))
        mag_valid = mag[valid]
        for p in range(12):
            chroma[p, i] = mag_valid[pitches == p].sum()
    # Normalize each frame
    norms = chroma.sum(axis=0, keepdims=True)
    norms[norms == 0] = 1.0
    return chroma / norms


def _load_cache() -> dict[str, dict[str, Any]]:
    """Load the analysis cache from disk."""
    if _CACHE_FILE.exists():
        try:
            return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Corrupted analysis cache, starting fresh.")
    return {}


def _save_cache(cache: dict[str, dict[str, Any]]) -> None:
    """Persist the analysis cache to disk."""
    _CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _clean_track_name(name: str) -> str:
    """Remove parenthetical/bracketed noise from a track name for better YouTube search.

    Strips sections like ``(feat. X)``, ``[Remastered 2024]``, ``(Deluxe Edition)``
    that pollute search results without adding value.
    """

    def _is_noise(match: re.Match[str]) -> str:
        text = match.group(0).lower()
        return "" if any(kw in text for kw in _TRACK_NOISE_KEYWORDS) else match.group(0)

    return _BRACKETED_RE.sub(_is_noise, name).strip()


class SpotifyPlaylistSorter:
    """Class for sorting Spotify playlists based on musical compatibility.

    This class analyzes track features (key, BPM, energy) and creates an optimized
    playlist order that provides smooth transitions between tracks.
    """

    def __init__(self, playlist_id: str, sp: spotipy.Spotify) -> None:
        """Initialize the playlist sorter.

        Args:
            playlist_id: Spotify playlist ID to sort
            sp: Authenticated spotipy.Spotify client
        """
        self.playlist_id = playlist_id
        self.sp = sp
        self.tracks_data: pd.DataFrame | None = None
        self.camelot_map = self._build_camelot_map()
        self.playlist_name: str | None = None
        self.original_track_order: list[str] | None = None
        self.original_items: list[str | None] = []
        self.snapshot_id: str | None = None

    def _build_camelot_map(self) -> dict[str, list[str]]:
        """Build a map of compatible Camelot keys."""
        camelot_map = {}
        numbers = range(CAMELOT_MIN_NUMBER, CAMELOT_MAX_NUMBER + 1)
        letters = ["A", "B"]

        for num in numbers:
            for letter in letters:
                key = f"{num}{letter}"
                neighbors = []

                # Same number, different letter (switching between minor/major)
                other_letter = "B" if letter == "A" else "A"
                neighbors.append(f"{num}{other_letter}")

                # Same letter, adjacent numbers
                prev_num = CAMELOT_MAX_NUMBER if num == CAMELOT_MIN_NUMBER else num - 1
                next_num = CAMELOT_MIN_NUMBER if num == CAMELOT_MAX_NUMBER else num + 1
                neighbors.extend([f"{prev_num}{letter}", f"{next_num}{letter}"])

                camelot_map[key] = neighbors

        return camelot_map

    def _fetch_tracks_from_spotify(self) -> list[dict[str, Any]]:
        """Fetch all tracks in the playlist from Spotify API."""
        tracks = []
        self.original_items = []
        results = self.sp.playlist_items(self.playlist_id)
        while results:
            for item in results["items"]:
                track = item.get("item") or item.get("track") or {}
                track_id = track.get("id")
                if track.get("type", "track") != "track" or track.get("is_local") or item.get("is_local"):
                    track_id = None
                self.original_items.append(track_id)
                if not track_id:
                    continue
                artist_names = ", ".join(a["name"] for a in track.get("artists", []))
                release_date = (track.get("album") or {}).get("release_date", "")
                tracks.append(
                    {
                        "id": track_id,
                        "Track": track["name"],
                        "Artist": artist_names,
                        "Popularity": track.get("popularity"),
                        "duration_ms": track.get("duration_ms"),
                        "release_year": release_date[:4] if release_date else "",
                    }
                )
            results = self.sp.next(results) if results.get("next") else None
        logger.info("Fetched %d tracks from Spotify playlist.", len(tracks))
        return tracks

    @staticmethod
    def _detect_key_mode(chroma_mean: np.ndarray) -> tuple[int, int]:
        """Detect musical key and mode via Krumhansl-Kessler profile correlation.

        Returns (pitch_class 0-11, mode 0=minor/1=major).
        """
        best_key, best_mode, best_corr = 0, 1, -float("inf")
        for pitch in range(12):
            for mode_idx, profile in enumerate([_KK_MINOR, _KK_MAJOR]):
                rotated = np.roll(profile, pitch)
                corr = float(np.corrcoef(chroma_mean, rotated)[0, 1])
                if corr > best_corr:
                    best_corr = corr
                    best_key = pitch
                    best_mode = mode_idx
        return best_key, best_mode

    @staticmethod
    def _analyze_track(
        sp_id: str,
        track_name: str,
        artist_name: str,
        duration_ms: int | None = None,
        release_year: str = "",
    ) -> dict[str, Any] | None:
        """Search YouTube via yt-dlp and analyze the first 30 s of audio.

        Args:
            sp_id: Spotify track ID (for logging).
            track_name: Track name from Spotify.
            artist_name: Comma-separated artist names from Spotify.
            duration_ms: Expected track duration from Spotify (milliseconds).
                Used to validate the YouTube result actually matches the track.
            release_year: Album release year (e.g. "2019") for search refinement.
        """
        clean_name = _clean_track_name(track_name)
        # Use all artists (space-separated) for a more specific search
        artists = " ".join(a.strip() for a in artist_name.split(","))
        year_part = f" {release_year}" if release_year else ""
        query = f"ytsearch10:{clean_name}{year_part} {artists}"
        expected_secs = duration_ms / 1000 if duration_ms else None

        result = SpotifyPlaylistSorter._download_and_load(query, track_name, sp_id, expected_secs)
        if result is None:
            return None
        y, sr = result

        # BPM
        bpm = float(_estimate_tempo(y, sr))

        # Key + mode via Krumhansl-Kessler
        chroma = _chroma_stft(y, sr)
        pitch_class, mode = SpotifyPlaylistSorter._detect_key_mode(chroma.mean(axis=1))
        camelot = _CAMELOT_MAP.get((pitch_class, mode))
        if camelot is None:
            logger.warning("Unknown key/mode (%d, %d) for '%s'", pitch_class, mode, track_name)
            return None

        # Raw RMS energy (normalized across playlist later)
        rms_mean = float(np.sqrt(np.mean(y**2)))

        return {"tempo": bpm, "energy": rms_mean, "key": pitch_class, "mode": mode, "camelot": camelot}

    @staticmethod
    def _download_and_load(  # noqa: C901, PLR0915
        query: str, track_name: str, sp_id: str, expected_secs: float | None
    ) -> tuple[np.ndarray, int] | None:
        """Search YouTube for candidates, pick the best duration match, download, and load audio.

        Searches for multiple results and selects the one whose duration is
        closest to the Spotify track.  This guarantees at least one match as
        long as YouTube returns any result.

        Returns ``None`` only when the search/download itself fails.
        """
        try:
            # --- Phase 1: search without downloading ---
            search_opts = {
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "noprogress": True,
                "skip_download": True,
                "ignoreerrors": True,
            }
            cookies_file = os.environ.get("YOUTUBE_COOKIES_FILE")
            if cookies_file and Path(cookies_file).is_file():
                # yt-dlp saves cookies on close; keep read-only mounts and parallel workers isolated.
                search_opts["cookiefile"] = StringIO(Path(cookies_file).read_text(encoding="utf-8"))
            with yt_dlp.YoutubeDL(search_opts) as ydl:
                info = ydl.extract_info(query, download=False)
            if not info:
                logger.warning("yt-dlp returned no results for '%s'", track_name)
                return None

            entries = info.get("entries") or [info]
            entries = [e for e in entries if e]
            if not entries:
                logger.warning("yt-dlp returned no results for '%s'", track_name)
                return None

            # --- Phase 2: pick best candidate by title + duration, views as tiebreaker ---
            clean_expected = _clean_track_name(track_name).lower()
            sp_lower = track_name.lower()
            sp_variants = {kw for kw in _VARIANT_KEYWORDS if kw in sp_lower}

            if len(entries) > 1:

                def _title_sim(entry: dict[str, Any]) -> float:
                    yt_title = _clean_track_name(entry.get("title") or "").lower()
                    return SequenceMatcher(None, clean_expected, yt_title).ratio()

                def _variant_penalty(entry: dict[str, Any]) -> float:
                    """Penalize when YouTube title has variant keywords the Spotify track doesn't (or vice versa)."""
                    yt_lower = (entry.get("title") or "").lower()
                    yt_variants = {kw for kw in _VARIANT_KEYWORDS if kw in yt_lower}
                    # Symmetric difference: keywords in one but not the other
                    mismatched = sp_variants ^ yt_variants
                    # Each mismatch adds a heavy penalty (capped at 1.0)
                    return min(len(mismatched) * 0.5, 1.0)

                def _dur_penalty(entry: dict[str, Any]) -> float:
                    if not expected_secs:
                        return 0.0
                    yt_dur = entry.get("duration") or 0
                    return min(abs(yt_dur - expected_secs) / max(expected_secs, 1), 1.0)

                def _preferred_bonus(entry: dict[str, Any]) -> float:
                    """Small bonus (negative penalty) for lyrical/official audio sources.

                    Only applies when the entry has NO variant mismatch — a "Remix Lyrics"
                    video should not benefit from the lyrics keyword.
                    """
                    yt_lower = (entry.get("title") or "").lower()
                    yt_variants = {kw for kw in _VARIANT_KEYWORDS if kw in yt_lower}
                    if sp_variants ^ yt_variants:
                        return 0.0
                    return -0.05 if any(kw in yt_lower for kw in _PREFERRED_KEYWORDS) else 0.0

                # Score: 40% title, 30% variant mismatch, 30% duration, with preferred bonus
                scored = [
                    (
                        e,
                        0.4 * (1.0 - _title_sim(e))
                        + 0.3 * _variant_penalty(e)
                        + 0.3 * _dur_penalty(e)
                        + _preferred_bonus(e),
                    )
                    for e in entries
                ]
                scored.sort(key=lambda x: x[1])

                # If the top candidates are close (within 0.05), use views to break the tie
                best_score = scored[0][1]
                _TIE_THRESHOLD = 0.05  # noqa: N806
                contenders = [(e, s) for e, s in scored if s - best_score <= _TIE_THRESHOLD]

                if len(contenders) > 1:
                    # Among near-ties, pick the one with the most views
                    contenders.sort(key=lambda x: x[0].get("view_count") or 0, reverse=True)
                    best_entry = contenders[0][0]
                    logger.info(
                        "YouTube match for '%s': '%s' (views=%s, score=%.2f, %d tied of %d)",
                        track_name,
                        best_entry.get("title", "?"),
                        f"{(best_entry.get('view_count') or 0):,}",
                        best_score,
                        len(contenders),
                        len(entries),
                    )
                else:
                    best_entry = scored[0][0]
                    logger.info(
                        "YouTube match for '%s': '%s' (views=%s, score=%.2f, %d candidates)",
                        track_name,
                        best_entry.get("title", "?"),
                        f"{(best_entry.get('view_count') or 0):,}",
                        best_score,
                        len(entries),
                    )
            else:
                best_entry = entries[0]

            video_url = best_entry.get("webpage_url") or best_entry.get("url")
            if not video_url:
                logger.warning("No URL found for best YouTube match for '%s'", track_name)
                return None

            # --- Phase 3: download the chosen video ---
            with tempfile.TemporaryDirectory() as tmpdir:
                dl_opts = {
                    "format": "bestaudio/best",
                    "outtmpl": str(Path(tmpdir) / "%(id)s.%(ext)s"),
                    "quiet": True,
                    "no_warnings": True,
                    "noplaylist": True,
                    "noprogress": True,
                    "retries": 3,
                    "socket_timeout": 30,
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "wav",
                            "preferredquality": "0",
                        },
                    ],
                }
                if cookies_file and Path(cookies_file).is_file():
                    dl_opts["cookiefile"] = StringIO(Path(cookies_file).read_text(encoding="utf-8"))
                with yt_dlp.YoutubeDL(dl_opts) as ydl:
                    ydl.extract_info(video_url, download=True)

                # Locate the downloaded file
                files = list(Path(tmpdir).iterdir())
                if not files:
                    logger.warning("yt-dlp downloaded nothing for '%s'", track_name)
                    return None
                filepath = str(files[0])

                return _load_audio(filepath, sr=22050, duration=30.0)
        except Exception:  # yt-dlp/audio loading raise many different error types
            logger.warning("Audio analysis failed for '%s' (%s)", track_name, sp_id, exc_info=True)
            return None

    def _fetch_audio_features_local(  # noqa: C901
        self, tracks: list[dict[str, Any]], progress_callback: Callable[[int, int], None] | None = None
    ) -> dict[str, dict[str, Any]]:
        """Analyze audio features for every track via yt-dlp + audio analysis.

        Args:
            tracks: Track dicts (must include ``Track`` and ``Artist`` keys).
            progress_callback: Optional callable ``(completed: int, total: int)``
                called after each track finishes analysis.
        """
        cache = _load_cache()
        features: dict[str, dict[str, Any]] = {}
        total = len(tracks)
        completed = 0

        # Separate cached vs uncached tracks
        uncached: list[dict[str, Any]] = []
        for track in tracks:
            sp_id = track["id"]
            if sp_id in cache:
                features[sp_id] = cache[sp_id]
                completed += 1
                if progress_callback is not None:
                    progress_callback(completed, total)
            else:
                uncached.append(track)

        if uncached:
            logger.info("Cache hit for %d/%d tracks, analyzing %d.", len(tracks) - len(uncached), total, len(uncached))

            def analyze_one(track: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
                return track["id"], self._analyze_track(
                    track["id"],
                    track["Track"],
                    track["Artist"],
                    track.get("duration_ms"),
                    track.get("release_year", ""),
                )

            with ThreadPoolExecutor(max_workers=_DEFAULT_MAX_WORKERS) as executor:
                futures = {executor.submit(analyze_one, t): t for t in uncached}
                for future in as_completed(futures):
                    sp_id, result = future.result()
                    if result is not None:
                        features[sp_id] = result
                        cache[sp_id] = result
                    completed += 1
                    if progress_callback is not None:
                        progress_callback(completed, total)

            _save_cache(cache)
        else:
            logger.info("All %d tracks found in cache, skipping analysis.", total)

        # Normalize energy 0-1 relative to the loudest track in this playlist
        if features:
            max_rms = max(v["energy"] for v in features.values())
            if max_rms > 0:
                for v in features.values():
                    v["energy"] = v["energy"] / max_rms

        logger.info("Locally analyzed %d/%d tracks.", len(features), len(tracks))
        return features

    def load_playlist(self, progress_callback: Callable[[int, int], None] | None = None) -> pd.DataFrame | None:
        """Load playlist name and track data using Spotify API + local audio analysis.

        Args:
            progress_callback: Optional callable ``(completed: int, total: int)``
                forwarded to the local audio-feature analysis step.
        """
        logger.info("Loading playlist metadata for: %s", self.playlist_id)
        try:
            playlist_info = self.sp.playlist(self.playlist_id, fields="name,snapshot_id")
            self.playlist_name = playlist_info["name"]
            self.snapshot_id = playlist_info["snapshot_id"]
            logger.info("Playlist Name (from Spotify): '%s'", self.playlist_name)
        except (spotipy.SpotifyException, KeyError, ValueError) as e:
            logger.warning("Failed to get playlist name from Spotify: %s. Will proceed without it.", e)
            self.playlist_name = f"Playlist {self.playlist_id}"

        # Get track list from Spotify
        spotify_tracks = self._fetch_tracks_from_spotify()
        if not spotify_tracks:
            logger.error("No tracks returned from Spotify. Cannot proceed.")
            self.tracks_data = pd.DataFrame()
            self.original_track_order = []
            return None

        # Analyze audio features locally via yt-dlp + audio analysis
        audio_features = self._fetch_audio_features_local(spotify_tracks, progress_callback=progress_callback)

        if not audio_features:
            logger.error("Local audio analysis returned no features. Cannot proceed.")
            self.tracks_data = pd.DataFrame()
            self.original_track_order = []
            return None

        # Merge track info with audio features
        rows = []
        for track in spotify_tracks:
            sp_id = track["id"]
            features = audio_features.get(sp_id)
            if features is None:
                logger.warning("No audio features for track '%s' (%s) — skipping.", track["Track"], sp_id)
                continue
            rows.append(
                {
                    "id": sp_id,
                    "Track": track["Track"],
                    "Artist": track["Artist"],
                    "Popularity": track.get("Popularity"),
                    "BPM": features.get("tempo"),
                    "Energy": features.get("energy"),
                    "Camelot": features.get("camelot"),
                    "Key": features.get("key"),
                }
            )

        if not rows:
            logger.error("No tracks had audio features available. Cannot proceed.")
            self.tracks_data = pd.DataFrame()
            self.original_track_order = []
            return None

        self.tracks_data = pd.DataFrame(rows)

        # Drop rows missing essential fields
        initial_count = len(self.tracks_data)
        self.tracks_data = self.tracks_data.dropna(subset=["id", "Camelot", "BPM", "Energy"])
        dropped = initial_count - len(self.tracks_data)
        if dropped > 0:
            logger.warning("Dropped %d tracks due to missing Camelot/BPM/Energy.", dropped)

        if self.tracks_data.empty:
            logger.error("No valid tracks remaining after filtering.")
            return None

        self.original_track_order = [t["id"] for t in spotify_tracks if t["id"] in self.tracks_data["id"].to_numpy()]

        logger.info("Loaded %d tracks with audio features.", len(self.tracks_data))
        return self.tracks_data

    def calculate_transition_score(self, track1: pd.Series, track2: pd.Series) -> float:  # noqa: C901, PLR0912, PLR0915
        """Calculate a transition score between two tracks based on key, BPM, and energy."""
        # Get track data
        key1 = track1.get("Camelot")
        key2 = track2.get("Camelot")
        bpm1 = track1.get("BPM")
        bpm2 = track2.get("BPM")
        energy1 = track1.get("Energy")
        energy2 = track2.get("Energy")

        # Key compatibility score (highest weight)
        key_score = 0.0
        key_compatible = False
        key_multiplier = 1.0  # Full weight

        if pd.isna(key1) or pd.isna(key2):
            # If either key is missing, reduce weight but don't penalize completely
            key_multiplier = 0.5
            if not pd.isna(key1) and key1 not in self.camelot_map:
                logger.debug("Key %s not in camelot map for score calc.", key1)
        else:
            key1_str = str(key1)
            key2_str = str(key2)
            if key1_str in self.camelot_map:
                key_compatible = key2_str in self.camelot_map[key1_str]

        # Perfect match (same key) is slightly better than compatible keys
        if not pd.isna(key1) and key1 == key2:
            key_score = 1.0
        elif key_compatible:
            key_score = 0.9  # Very good but not perfect
        else:
            key_score = 0.1  # Poor key compatibility

        # BPM score - closer is better, within 5 BPM is great
        bpm_score = 0.0
        if not pd.isna(bpm1) and not pd.isna(bpm2):
            try:
                # Convert BPM values to float
                bpm1_val = float(bpm1)
                bpm2_val = float(bpm2)
                if bpm1_val > 0 and bpm2_val > 0:
                    bpm_diff = abs(bpm1_val - bpm2_val)
                    if bpm_diff <= BPM_GOOD_THRESHOLD:
                        bpm_score = 1.0
                    elif bpm_diff <= BPM_MEDIUM_THRESHOLD:
                        bpm_score = 0.7
                    else:
                        # Gradually scale down as BPM difference increases
                        bpm_score = max(0, 1 - (bpm_diff - BPM_MEDIUM_THRESHOLD) / 20)
            except (ValueError, TypeError):
                # Handle case where BPM cannot be converted to float
                logger.debug("Cannot convert BPM to float for scoring: %s, %s", bpm1, bpm2)

        # Energy flow score - slight increase is good, big jumps are bad
        energy_score = 0.0
        if not pd.isna(energy1) and not pd.isna(energy2):
            try:
                # Convert energy values to float
                energy1_val = float(energy1)
                energy2_val = float(energy2)
                energy_diff = energy2_val - energy1_val  # Positive for increasing energy
                # Small energy increases are ideal
                if 0 <= energy_diff <= ENERGY_SMALL_INCREASE_MAX:
                    energy_score = 1.0
                # Small decreases or moderate increases are ok
                elif (
                    ENERGY_SMALL_DECREASE_MIN <= energy_diff < 0
                    or ENERGY_SMALL_INCREASE_MAX < energy_diff <= ENERGY_MODERATE_INCREASE_MAX
                ):
                    energy_score = 0.7
                # Big jumps are scored lower
                else:
                    energy_score = max(0, 1 - abs(energy_diff) / ENERGY_SCALING_FACTOR)
            except (ValueError, TypeError):
                # Handle case where energy cannot be converted to float
                logger.debug("Cannot convert Energy to float for scoring: %s, %s", energy1, energy2)

        # Weight the scores and apply the key multiplier
        # Key is weighted most heavily since harmonic compatibility is paramount
        return key_score * 0.5 * key_multiplier + bpm_score * 0.3 + energy_score * 0.2

    def sort_playlist(self, start_track_id: str) -> list[str]:  # noqa: C901
        """Sort the playlist using transition scores, starting from anchor."""
        if self.tracks_data is None or self.tracks_data.empty:
            logger.error("Track data is not loaded or is empty. Cannot sort.")
            return []

        sortable_tracks = self.tracks_data.copy()

        if start_track_id not in sortable_tracks["id"].to_numpy():
            logger.error("Start track ID '%s' not found in the loaded & filtered tracks.", start_track_id)
            if self.original_track_order and start_track_id in self.original_track_order:
                logger.warning(
                    "Anchor track was present initially but filtered out due to missing data. Cannot use as anchor."
                )
            return []

        logger.info("Starting sort with anchor track ID: %s", start_track_id)
        current_id = start_track_id
        sorted_ids = [current_id]
        remaining_ids = set(sortable_tracks["id"].tolist())
        remaining_ids.remove(current_id)
        initial_sortable_ids = remaining_ids.copy()

        while remaining_ids:
            # Get current track data
            current_track_data = sortable_tracks[sortable_tracks["id"] == current_id]
            if current_track_data.empty:
                logger.error("Could not find data for current track ID: %s. Stopping sort.", current_id)
                break
            current_track = current_track_data.iloc[0]

            # Calculate scores for all remaining tracks
            scores = pd.Series(index=sortable_tracks.index, dtype=float)

            for idx, row in sortable_tracks.iterrows():
                if row["id"] in remaining_ids:
                    scores[idx] = self.calculate_transition_score(current_track, row)
                else:
                    scores[idx] = np.nan

            if scores.empty or scores.isna().all():
                logger.warning(
                    "Could not calculate valid scores from %s. Stopping sort.", current_track.get("Track", current_id)
                )
                break

            # Get next track with highest score
            next_track_idx = scores.idxmax()
            next_track = sortable_tracks.loc[next_track_idx]
            next_track_id = str(next_track["id"])

            if next_track_id not in remaining_ids:
                # This should not happen but protect against it
                break

            # Add to sorted list and update for next iteration
            sorted_ids.append(next_track_id)
            remaining_ids.remove(next_track_id)
            current_id = next_track_id
            logger.debug("Added: %s (Score: %.2f)", next_track.get("Track", current_id), scores.loc[next_track_idx])

        original_ids_set = set(self.original_track_order) if self.original_track_order else set()
        missing_from_sort = original_ids_set - set(sorted_ids)

        if missing_from_sort and self.original_track_order:
            logger.warning("Sort finished, but %s tracks that had data were not placed.", len(missing_from_sort))
            missing_tracks_ordered = [tid for tid in self.original_track_order if tid in missing_from_sort]
            logger.info("Appending %s tracks that were not placed during sorting.", len(missing_tracks_ordered))
            sorted_ids.extend(missing_tracks_ordered)
        elif len(sorted_ids) < len(initial_sortable_ids) + 1:
            logger.warning(
                "Sorting ended with %s tracks, but started with %s sortable tracks.",
                len(sorted_ids),
                len(initial_sortable_ids),
            )

        logger.info("Playlist sorting complete. Final track count: %s", len(sorted_ids))
        counts = Counter(self.original_track_order)
        return [track_id for track_id in sorted_ids for _ in range(counts[track_id])]

    def compare_playlists(self, sorted_ids: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Compare original (scraped order) and sorted playlist."""
        if self.tracks_data is None or self.tracks_data.empty or not self.original_track_order:
            logger.error("Cannot compare playlists: Data not loaded or original order missing.")
            return pd.DataFrame(), pd.DataFrame()

        # Check if we have valid IDs to work with
        valid_original_ids = [tid for tid in self.original_track_order if tid in self.tracks_data["id"].to_numpy()]
        valid_sorted_ids = [tid for tid in sorted_ids if tid in self.tracks_data["id"].to_numpy()]

        if not valid_original_ids or not valid_sorted_ids:
            logger.error("No valid track data found for comparison after filtering.")
            return pd.DataFrame(), pd.DataFrame()

        # Create DataFrames for the two orderings
        original_df = pd.DataFrame(index=range(len(valid_original_ids)))
        sorted_df = pd.DataFrame(index=range(len(valid_sorted_ids)))

        # Populate columns with track data
        for df, id_list in [(original_df, valid_original_ids), (sorted_df, valid_sorted_ids)]:
            id_col, track_col, artist_col, camelot_col, bpm_col, energy_col = [], [], [], [], [], []

            for track_id in id_list:
                track_data = self.tracks_data[self.tracks_data["id"] == track_id]
                if track_data.empty:
                    continue

                id_col.append(track_id)
                track_col.append(track_data["Track"].iloc[0])
                artist_col.append(track_data["Artist"].iloc[0])
                camelot_col.append(track_data["Camelot"].iloc[0])
                bpm_col.append(track_data["BPM"].iloc[0])
                energy_col.append(track_data["Energy"].iloc[0])

            df["id"] = id_col
            df["Track"] = track_col
            df["Artist"] = artist_col
            df["Camelot"] = camelot_col
            df["BPM"] = bpm_col
            df["Energy"] = energy_col

        return original_df, sorted_df

    def get_transition_analysis(self, sorted_ids: list[str]) -> list[dict[str, Any]]:  # noqa: C901
        """Generate analysis of the transitions in the sorted playlist."""
        if self.tracks_data is None or self.tracks_data.empty:
            logger.warning("No track data to analyze transitions.")
            return []

        valid_ids = [tid for tid in sorted_ids if tid in self.tracks_data["id"].to_numpy()]

        if len(valid_ids) < MIN_TRANSITION_COUNT:
            return []

        transitions = []

        for i in range(len(valid_ids) - 1):
            track1_id = valid_ids[i]
            track2_id = valid_ids[i + 1]

            track1_data = self.tracks_data[self.tracks_data["id"] == track1_id].iloc[0]
            track2_data = self.tracks_data[self.tracks_data["id"] == track2_id].iloc[0]

            key1 = track1_data.get("Camelot")
            key2 = track2_data.get("Camelot")
            bpm1 = track1_data.get("BPM")
            bpm2 = track2_data.get("BPM")
            energy1 = track1_data.get("Energy")
            energy2 = track2_data.get("Energy")

            transition = {
                "index": i + 1,
                "track1_id": track1_id,
                "track2_id": track2_id,
                "track1_name": track1_data.get("Track", "Unknown"),
                "track2_name": track2_data.get("Track", "Unknown"),
                "track1_artist": track1_data.get("Artist", "Unknown"),
                "track2_artist": track2_data.get("Artist", "Unknown"),
                "key1": key1,
                "key2": key2,
                "bpm1": bpm1,
                "bpm2": bpm2,
                "energy1": energy1,
                "energy2": energy2,
            }

            # Skip this transition if critical data is missing
            if pd.isna(key1) or pd.isna(key2):
                transition["message"] = "Missing key information, cannot analyze compatibility"
                transitions.append(transition)
                continue

            if pd.isna(bpm1) or pd.isna(bpm2):
                transition["message"] = "Missing BPM information, cannot analyze tempo change"
                transitions.append(transition)
                continue

            # Check key compatibility
            key_compatible = False
            perfect_key_match = key1 == key2

            if not pd.isna(key1) and str(key1) in self.camelot_map:
                key_compatible = str(key2) in self.camelot_map[str(key1)]

            # Calculate BPM difference
            bpm_diff = None
            if not pd.isna(bpm1) and not pd.isna(bpm2):
                try:
                    bpm_diff = abs(float(bpm1) - float(bpm2))
                except (ValueError, TypeError):
                    logger.debug("Cannot convert BPM to float for analysis: %s, %s", bpm1, bpm2)

            # Calculate energy difference
            energy_diff = None
            if not pd.isna(energy1) and not pd.isna(energy2):
                try:
                    energy_diff = float(energy2) - float(energy1)
                except (ValueError, TypeError):
                    logger.debug("Cannot convert Energy to float for analysis: %s, %s", energy1, energy2)

            # Add compatibility details
            transition["key_compatible"] = key_compatible
            transition["perfect_key_match"] = perfect_key_match
            transition["bpm_diff"] = bpm_diff
            transition["energy_diff"] = energy_diff

            # Calculate overall transition score
            transition["score"] = self.calculate_transition_score(track1_data, track2_data)

            transitions.append(transition)

        return transitions

    def update_spotify_playlist(self, sorted_ids: list[str]) -> tuple[bool, str]:
        """Move existing occurrences without deleting duplicates or unanalyzed songs."""
        if not self.snapshot_id or not sorted_ids or Counter(sorted_ids) != Counter(self.original_track_order):
            return False, "Check the playlist again before saving."

        positions: dict[str, deque[int]] = defaultdict(deque)
        for index, track_id in enumerate(self.original_items):
            if track_id in sorted_ids:
                positions[track_id].append(index)
        if sum(map(len, positions.values())) != len(sorted_ids):
            return False, "The song list changed. Check the playlist again."
        ordered_positions = iter(positions[track_id].popleft() for track_id in sorted_ids)
        target = [
            next(ordered_positions) if track_id in positions else index
            for index, track_id in enumerate(self.original_items)
        ]
        current = list(range(len(target)))
        try:
            latest = self.sp.playlist(self.playlist_id, fields="snapshot_id")["snapshot_id"]
            if latest != self.snapshot_id:
                return False, "This playlist changed on Spotify. Check it again before saving."
            # ponytail: one request per moved song; batch adjacent moves if save time becomes a problem.
            for destination, original_position in enumerate(target):
                source = current.index(original_position)
                if source == destination:
                    continue
                result = self.sp.playlist_reorder_items(
                    self.playlist_id, source, destination, snapshot_id=self.snapshot_id
                )
                self.snapshot_id = result["snapshot_id"]
                current.insert(destination, current.pop(source))
        except Exception:
            logger.exception("Could not finish reordering playlist %s", self.playlist_id)
            self.snapshot_id = None
            return False, "Saving stopped. Some songs may have moved. Check the playlist again before saving."
        else:
            self.original_items = [self.original_items[index] for index in target]
            return True, "Saved to Spotify."
