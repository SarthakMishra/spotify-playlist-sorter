"""Spotify playlist analysis and constrained arrangements."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import secrets
import tempfile
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from pathlib import Path
from threading import Event
from time import perf_counter, sleep
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
import pandas as pd
import spotipy
import yt_dlp

from app.audio_analysis import ANALYSIS_VERSION, MAX_SECONDS, SETTINGS, analyze_audio, load_audio
from app.youtube import SHARED_FAILURES, SourceAccessError, configured_cookies, failure_reason, youtube_options

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)
_CACHE_FILE = Path(__file__).resolve().parent.parent / ".analysis_cache.json"
_CACHE_SCHEMA = 2
_RESOLVER_VERSION = 3
_MATCH_SCORE = 0.75
_STRUCTURED_TITLE_SIMILARITY = 0.85
_VERIFIED_TITLE_SIMILARITY = 0.9
_SHORTLIST_SIMILARITY = 0.65
_CACHE_CHECKPOINT = 10
_VARIANTS = {
    "live": r"\b(?:live|concert)\b",
    "remix": r"\bremix(?:ed)?\b",
    "karaoke": r"\bkaraoke\b",
    "instrumental": r"\binstrumental\b",
    "cover": r"\bcover\b",
    "acoustic": r"\b(?:acoustic|unplugged)\b",
    "radio": r"\bradio (?:edit|version)\b",
    "extended": r"\bextended\b",
    "edit": r"\bedit\b",
    "demo": r"\bdemo\b",
    "remaster": r"\bremaster(?:ed)?\b",
    "slowed": r"\bslowed\b",
    "sped_up": r"\b(?:sped|speed) up\b",
    "reverb": r"\breverb(?:ed)?\b",
    "mashup": r"\bmash ?up\b",
    "lofi": r"\blo ?fi\b",
    "8d": r"\b8d\b",
    "bass_boosted": r"\bbass boosted\b",
}


def _normalize_text(value: str) -> str:
    """Normalize case and punctuation while preserving words and edition information."""
    text = "".join(char for char in unicodedata.normalize("NFKD", value) if not unicodedata.combining(char))
    return " ".join(re.sub(r"[\W_]+", " ", text.casefold()).split())


def _variants(title: str) -> set[str]:
    """Recognize version qualifiers without substring matches such as live in alive."""
    text = _normalize_text(title)
    tags = {name for name, pattern in _VARIANTS.items() if re.search(pattern, text)}
    if tags & {"remaster", "edit", "demo"}:
        tags.update(re.findall(r"\b(?:19|20)\d{2}\b", text))
    return tags


def _metadata(track: dict[str, Any]) -> dict[str, Any]:
    """Bind cached measurements to the exact requested recording metadata."""
    return {
        "id": track["id"],
        "title": track["Track"],
        "artists": track.get("artist_names") or [track.get("Artist", "")],
        "duration_ms": track.get("duration_ms"),
        "release_year": track.get("release_year", ""),
        "album": track.get("album", ""),
    }


def _positive_number(value: object) -> float | None:
    """Reject missing, non-finite or non-positive source duration values."""
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result > 0 else None


def _title_text(title: str) -> str:
    """Normalize recording titles while retaining version qualifiers and genuine title words."""
    title = re.sub(r"\s*[-([]\s*from\s+.*", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*[-([]\s*(?:album version|original version|original mix)\b.*", "", title, flags=re.IGNORECASE)
    title = re.sub(r"[([]\s*(?:feat\.?|ft\.?|featuring)\s+[^)\]]+[)\]]", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\b(?:feat\.?|ft\.?|featuring)\s+[^([\-]*", "", title, flags=re.IGNORECASE)
    return _normalize_text(title)


def _candidate_title(entry: dict[str, Any], artists: list[str]) -> str:
    """Keep structured track names intact; strip artists only from upload-title prefixes."""
    if entry.get("track"):
        return _title_text(entry["track"])
    title = _title_text(entry.get("title") or "")
    for artist in artists:
        if title.startswith(artist + " "):
            title = title[len(artist) :].strip()
    return re.sub(r"\s+(?:official(?: music)? (?:audio|video)|lyric(?:s| video)?|hd|hq)$", "", title).strip()


def _title_similarity(entry: dict[str, Any], metadata: dict[str, Any]) -> float:
    """Recognize the requested title inside upload decoration, without changing known track names."""
    artists = [_normalize_text(artist) for artist in metadata["artists"]]
    title = _title_text(metadata["title"])
    candidate = _candidate_title(entry, artists)
    similarity = SequenceMatcher(None, title, candidate).ratio()
    if not entry.get("track") and title and f" {title} " in f" {candidate} ":
        similarity = max(similarity, 0.94)
    return similarity


def _artist_present(artist: str, evidence: str) -> bool:
    """Match credited names and common official-channel spellings such as ACDCVEVO."""
    artist, evidence = _normalize_text(artist), _normalize_text(evidence)
    if f" {artist} " in f" {evidence} ":
        return True
    compact = artist.replace(" ", "")
    return evidence.replace(" ", "") in {compact, compact + "vevo", compact + "topic"}


def _duration_tolerance(seconds: float) -> float:
    """Allow modest upload padding for best-effort matches without accepting much longer cuts."""
    return max(3.0, min(20.0, seconds * 0.08))


def _shortlist(entries: list[dict[str, Any]], metadata: dict[str, Any]) -> list[dict[str, Any]]:
    """Filter flat search metadata before spending requests on at most three videos."""
    artists = [_normalize_text(artist) for artist in metadata["artists"]]
    expected = float(metadata["duration_ms"]) / 1000
    candidates = {}
    for entry in entries[:10]:
        if not isinstance(entry, dict) or not isinstance(entry.get("title"), str):
            continue
        source_id = entry.get("id", "")
        if not isinstance(source_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", source_id) or entry.get("is_live"):
            continue
        duration = _positive_number(entry.get("duration"))
        if duration is not None and abs(duration - expected) > _duration_tolerance(expected):
            continue
        title = _candidate_title(entry, artists)
        if _variants(title) != _variants(_title_text(metadata["title"])):
            continue
        similarity = _title_similarity(entry, metadata)
        if similarity < _SHORTLIST_SIMILARITY:
            continue
        channel = _normalize_text(str(entry.get("channel") or entry.get("uploader") or ""))
        provenance = channel.endswith(" topic") or bool(entry.get("channel_is_verified"))
        candidates[source_id] = (similarity + 0.1 * provenance, entry)
    return [item[1] for item in sorted(candidates.values(), key=lambda item: -item[0])[:3]]


def _rank_recordings(entries: list[dict[str, Any]], metadata: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate full recording metadata, distinguishing music credits from upload text."""
    # ponytail: metadata cannot prove audio identity; add authorized fingerprints if reviewed false matches warrant it.
    duration_ms = _positive_number(metadata["duration_ms"])
    artists = [_normalize_text(artist) for artist in metadata["artists"]]
    if duration_ms is None or not artists or not all(artists):
        return []
    expected = duration_ms / 1000
    title = _title_text(metadata["title"])
    eligible: dict[str, dict[str, Any]] = {}
    for entry in entries[:10]:
        if not isinstance(entry, dict) or not isinstance(entry.get("title"), str):
            continue
        source_id = entry.get("id", "")
        duration = _positive_number(entry.get("duration"))
        if not isinstance(source_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", source_id) or duration is None:
            continue
        tolerance = _duration_tolerance(expected)
        difference = abs(duration - expected)
        source_title = entry["title"]
        candidate_title = _candidate_title(entry, artists)
        # Upload labels can contradict otherwise clean structured music metadata.
        upload_title = _candidate_title({"title": source_title}, artists)
        if (
            difference > tolerance
            or _variants(candidate_title) != _variants(title)
            or _variants(upload_title) != _variants(title)
        ):
            continue
        artist_credits = entry.get("artists") or [entry.get("artist") or ""]
        if isinstance(artist_credits, str):
            artist_credits = [artist_credits]
        credited = " " + _normalize_text(" ".join(str(artist) for artist in artist_credits)) + " "
        if credited.strip() and not any(_artist_present(artist, credited) for artist in artists):
            continue
        evidence = (
            " "
            + _normalize_text(
                source_title + " " + credited + " " + str(entry.get("uploader") or entry.get("channel") or "")
            )
            + " "
        )
        similarity = _title_similarity(entry, metadata)
        if entry.get("track") and similarity < _STRUCTURED_TITLE_SIMILARITY:
            continue
        channel = str(entry.get("channel") or entry.get("uploader") or "")
        artist_fraction = sum(
            _artist_present(artist, evidence) or _artist_present(artist, channel) for artist in artists
        ) / len(artists)
        if not artist_fraction and not (entry.get("channel_is_verified") and similarity >= _VERIFIED_TITLE_SIMILARITY):
            continue
        score = 0.5 * similarity + 0.25 + 0.05 * artist_fraction + 0.2 * (1 - difference / tolerance)
        music_metadata = bool(
            entry.get("track")
            and candidate_title == title
            and all(f" {artist} " in credited for artist in artists)
            and metadata.get("album")
            and _normalize_text(str(entry.get("album") or "")) == _normalize_text(metadata["album"])
        )
        eligible[source_id] = {
            "id": source_id,
            "url": f"https://www.youtube.com/watch?v={source_id}",
            "title": source_title,
            "duration": duration,
            "score": score,
            "evidence": {
                "title_similarity": similarity,
                "artists": metadata["artists"],
                "duration_difference": difference,
                "variants": sorted(_variants(candidate_title)),
                "music_metadata": music_metadata,
                "artist_coverage": artist_fraction,
                "verified_channel": bool(entry.get("channel_is_verified")),
            },
        }
    return sorted(
        eligible.values(),
        key=lambda item: (
            -item["evidence"]["music_metadata"],
            -item["score"],
            -item["evidence"]["verified_channel"],
            item["id"],
        ),
    )


def _select_recording(ranked: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Use the best eligible recording even when several uploads have similar scores."""
    return ranked[0] if ranked and ranked[0]["score"] >= _MATCH_SCORE else None


def _source_fingerprint(source: dict[str, Any]) -> str:
    """Detect source-record changes before reusing their stored measurements."""
    return hashlib.sha256(json.dumps(source, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _load_cache() -> dict[str, dict[str, Any]]:
    """Ignore unversioned, incompatible or damaged analysis caches."""
    try:
        data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or any(
            data.get(key) != value
            for key, value in (
                ("schema", _CACHE_SCHEMA),
                ("analysis_version", ANALYSIS_VERSION),
                ("settings", SETTINGS),
            )
        ):
            return {}
        # Version 2 accepted a stricter subset; its successful analyses remain valid.
        if data.get("resolver_version") not in {2, _RESOLVER_VERSION}:
            return {}
        records = data.get("records")
        return records if isinstance(records, dict) else {}
    except (ValueError, OSError):
        return {}


def _save_cache(records: dict[str, dict[str, Any]]) -> None:
    """Replace the cache atomically so interruption cannot leave a partial JSON file."""
    # ponytail: one JSON file; use SQLite if its size makes checkpoints slow.
    path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=_CACHE_FILE.parent, delete=False) as output:
            path = Path(output.name)
            json.dump(
                {
                    "schema": _CACHE_SCHEMA,
                    "analysis_version": ANALYSIS_VERSION,
                    "resolver_version": _RESOLVER_VERSION,
                    "settings": SETTINGS,
                    "records": records,
                },
                output,
                allow_nan=False,
            )
        path.replace(_CACHE_FILE)
    finally:
        if path is not None:
            path.unlink(missing_ok=True)


def _cache_matches(record: object, metadata: dict[str, Any]) -> bool:
    """Require matching input metadata, complete measurements and unchanged source evidence."""
    if not isinstance(record, dict) or record.get("status") != "ready" or record.get("metadata") != metadata:
        return False
    source = record.get("source")
    analysis = record.get("analysis")
    if not isinstance(source, dict) or not isinstance(analysis, dict):
        return False
    summary = analysis.get("summary")
    if not isinstance(summary, dict) or not {"rms_db", "onset", "tempo", "camelot"} <= summary.keys():
        return False
    if not isinstance(summary["rms_db"], (int, float)) or not math.isfinite(summary["rms_db"]):
        return False
    try:
        fingerprint = record.get("source_fingerprint")
        return isinstance(fingerprint, str) and fingerprint == _source_fingerprint(source)
    except (ValueError, TypeError):
        return False


def _with_intensity(records: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Derive playlist-relative intensity without altering cached raw measurements."""
    ready = {key: record for key, record in records.items() if record.get("status") == "ready"}
    result = records.copy()
    if ready:
        values = np.array(
            [[r["analysis"]["summary"]["rms_db"], r["analysis"]["summary"]["onset"]] for r in ready.values()],
            dtype=float,
        )
        normalized = np.full_like(values, 0.5)
        for column in range(values.shape[1]):
            valid = np.isfinite(values[:, column])
            if valid.any():
                low, high = np.percentile(values[valid, column], [5, 95])
                if high > low:
                    normalized[valid, column] = np.clip((values[valid, column] - low) / (high - low), 0, 1)
        for (key, record), components in zip(ready.items(), normalized, strict=True):
            summary = record["analysis"]["summary"]
            result[key] = {
                **record,
                "tempo": summary["tempo"],
                "camelot": summary["camelot"],
                "energy": float(components @ np.array([0.6, 0.4])),
            }
    return result


Profile = Literal["smooth", "variety"]
_PROFILE_WEIGHTS = {"smooth": (0.80, 0.15, 0.05), "variety": (0.60, 0.25, 0.15)}
_COMPONENTS = ("tempo", "intensity", "texture", "chroma")
_SCORING_VERSION = 1
_MAX_MATRIX_ENTRIES = 1000
_MAX_EVALUATIONS = 5000
_MONOTONY_THRESHOLD = 0.15
_ARTIST_WINDOW = 3
_MONOTONY_WINDOW = 5
_MIN_NOTE_EVIDENCE = 0.5
_INTENSITY_NOTE_CHANGE = 0.2


def _audio_note(transition: dict[str, Any]) -> tuple[float, str] | None:
    """Describe a supported boundary change without turning cost into a preference claim."""
    notes = []
    evidence = transition["evidence"]
    delta = transition["energy_diff"]
    if evidence["intensity"] >= _MIN_NOTE_EVIDENCE and delta is not None and abs(delta) >= _INTENSITY_NOTE_CHANGE:
        text = (
            "Intensity rises from this ending into the next opening."
            if delta > 0
            else "Intensity drops from this ending into the next opening."
        )
        notes.append((abs(delta) * evidence["intensity"], text))
    for component, threshold, text in (
        ("tempo", 0.15, "The estimated pace changes between these songs."),
        ("texture", 0.35, "The ending and next opening have different sound textures."),
        ("chroma", 0.4, "The tonal character changes between these songs."),
    ):
        quality = evidence[component]
        cost = transition["components"][component]
        if quality >= _MIN_NOTE_EVIDENCE and cost is not None:
            # Remove the neutral uncertainty prior before deciding whether a change stands out.
            difference = max(0.0, (cost - (1 - quality) * 0.5) / quality)
            if difference >= threshold:
                notes.append((difference * quality, text))
    return max(notes, key=lambda note: note[0]) if notes else None


def _pin_error(entries: list[dict[str, Any]], first: str | None, last: str | None) -> str | None:
    """Validate absolute endpoint requirements against the loaded occurrences."""
    identities = {entry["occurrence"]: index for index, entry in enumerate(entries)}
    if not entries or len(identities) != len(entries):
        return "Check the playlist again before arranging it."
    if first is not None and first == last:
        return "Choose different entries for the first and last songs."
    for position, chosen in ((0, first), (len(entries) - 1, last)):
        if chosen is None:
            continue
        if chosen not in identities:
            return "Choose a song from this playlist."
        source = identities[chosen]
        if source != position and (entries[source]["fixed_reason"] or entries[position]["fixed_reason"]):
            return "A song kept in place cannot move or give its position to another song."
    return None


def _feasible_order(
    entries: list[dict[str, Any]], first: str | None, last: str | None
) -> tuple[np.ndarray, np.ndarray]:
    """Place endpoints and fill remaining movable slots in their original relative order."""
    identities = {entry["occurrence"]: index for index, entry in enumerate(entries)}
    locked = {i: i for i, entry in enumerate(entries) if entry["fixed_reason"]}
    for position, chosen in ((0, first), (len(entries) - 1, last)):
        if chosen is not None:
            locked[position] = identities[chosen]
    free = np.array([i for i in range(len(entries)) if i not in locked], dtype=int)
    used = set(locked.values())
    available = iter(i for i in range(len(entries)) if i not in used)
    order = np.array([locked[i] if i in locked else next(available) for i in range(len(entries))], dtype=int)
    return order, free


def _segment_rows(segments: list[dict[str, Any]]) -> dict[str, np.ndarray]:
    """Pack numeric measurements, with zero evidence for missing or invalid values."""
    values, evidence, chroma, chroma_evidence = [], [], [], []
    for segment in segments:
        support = segment.get("evidence", {})
        contrast = segment.get("contrast") or [None] * 7
        values.append([segment.get(key) for key in ("tempo", "rms_db", "onset", "centroid")] + contrast)
        evidence.append(
            [support.get(key, 0) for key in ("tempo", "rms_db", "onset", "centroid")] + [support.get("contrast", 0)] * 7
        )
        chroma.append(segment.get("chroma") or [0.0] * 12)
        chroma_evidence.append(support.get("chroma", 0))
    raw = np.asarray(values, dtype=float)
    quality = np.clip(np.nan_to_num(np.asarray(evidence, dtype=float), nan=0, posinf=0, neginf=0), 0, 1)
    quality[~np.isfinite(raw)] = 0
    quality[raw[:, 0] <= 0, 0] = 0
    tones = np.asarray(chroma, dtype=float)
    norms = np.linalg.norm(tones, axis=1)
    tonal_quality = np.clip(np.nan_to_num(np.asarray(chroma_evidence, dtype=float), nan=0, posinf=0, neginf=0), 0, 1)
    tonal_quality[(norms <= 0) | ~np.isfinite(tones).all(axis=1)] = 0
    tones = np.nan_to_num(tones / np.maximum(norms[:, None], 1e-12), nan=0, posinf=0, neginf=0)
    return {"raw": raw, "quality": quality, "chroma": tones, "chroma_quality": tonal_quality}


def _pair_components(
    left: dict[str, np.ndarray], right: dict[str, np.ndarray]
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Compute directed ending/beginning distances with a neutral prior for uncertain terms."""
    costs, evidence = {}, {}
    a = np.log2(np.where(left["quality"][:, 0] > 0, left["raw"][:, 0], 1))
    b = np.log2(np.where(right["quality"][:, 0] > 0, right["raw"][:, 0], 1))
    ratio = a[:, None] - b[None, :]
    tempo = np.clip(np.minimum.reduce([abs(ratio), abs(ratio - 1), abs(ratio + 1)]), 0, 1)
    evidence["tempo"] = np.minimum(left["quality"][:, 0, None], right["quality"][None, :, 0])
    evidence["intensity"] = np.minimum(left["intensity_quality"][:, None], right["intensity_quality"][None, :])
    intensity = abs(left["intensity"][:, None] - right["intensity"][None, :])
    for key, distance in (("tempo", tempo), ("intensity", intensity)):
        costs[key] = evidence[key] * distance + (1 - evidence[key]) * 0.5
    texture, texture_quality = [], []
    for column in range(3, left["raw"].shape[1]):
        quality = np.minimum(left["quality"][:, column, None], right["quality"][None, :, column])
        distance = abs(left["normalized"][:, column, None] - right["normalized"][None, :, column])
        texture.append(quality * distance + (1 - quality) * 0.5)
        texture_quality.append(quality)
    costs["texture"], evidence["texture"] = np.mean(texture, axis=0), np.mean(texture_quality, axis=0)
    tonal = np.clip(1 - left["chroma"] @ right["chroma"].T, 0, 1)
    evidence["chroma"] = np.minimum(left["chroma_quality"][:, None], right["chroma_quality"][None, :])
    costs["chroma"] = evidence["chroma"] * tonal + (1 - evidence["chroma"]) * 0.5
    return costs, evidence


def _prepare_arrangement(entries: list[dict[str, Any]], features: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Prepare shared normalization and pair matrices once for a loaded analysis."""
    analyses = [
        features.get(entry["id"], {}).get("analysis", {}) if not entry["fixed_reason"] else {} for entry in entries
    ]
    parts = {
        name: _segment_rows([analysis.get(name) or {} for analysis in analyses])
        for name in ("intro", "outro", "body", "summary")
    }
    unique = list({entry["id"]: i for i, entry in enumerate(entries) if not entry["fixed_reason"]}.values())
    samples = np.concatenate([part["raw"][unique] for part in parts.values()])
    support = np.concatenate([part["quality"][unique] for part in parts.values()])
    low, high = np.zeros(samples.shape[1]), np.zeros(samples.shape[1])
    for column in range(1, samples.shape[1]):
        valid = (support[:, column] > 0) & np.isfinite(samples[:, column])
        if valid.any():
            low[column], high[column] = np.percentile(samples[valid, column], [5, 95])
    for part in parts.values():
        normalized = np.clip((part["raw"] - low) / np.where(high > low, high - low, 1), 0, 1)
        part["normalized"] = np.where((part["quality"] > 0) & (high > low), normalized, 0.5)
        part["intensity"] = part["normalized"][:, 1:3] @ np.array([0.6, 0.4])
        part["intensity_quality"] = part["quality"][:, 1:3] @ np.array([0.6, 0.4])
    components, evidence = _pair_components(parts["outro"], parts["intro"])
    body, _ = _pair_components(parts["body"], parts["body"])
    shared = np.zeros((len(entries), len(entries)), dtype=bool)
    positions: dict[str, list[int]] = {}
    for index, entry in enumerate(entries):
        artists = entry.get("artist_ids") or [
            f"name:{_normalize_text(name)}" for name in entry.get("artist_names", []) if name
        ]
        for artist in set(artists):
            positions.setdefault(artist, []).append(index)
    for indices in positions.values():
        shared[np.ix_(indices, indices)] = True
    assessed = sum(evidence.values()) > 0
    transition = sum(components[key] * weight for key, weight in zip(_COMPONENTS, (0.3, 0.3, 0.3, 0.1), strict=True))
    return {
        "parts": parts,
        "components": components,
        "evidence": evidence,
        "artists": shared,
        "transition": np.where(assessed, transition, 0.5),
        "body": (body["tempo"] + body["intensity"] + body["texture"]) / 3,
        "assessed": assessed,
    }


def _order_terms(order: np.ndarray, data: dict[str, Any]) -> dict[str, float]:
    """Evaluate every actual edge and repetition/monotony window in the complete order."""
    repeats = np.zeros(len(order))
    for distance in range(1, min(_ARTIST_WINDOW + 1, len(order))):
        repeats[distance:] = np.maximum(
            repeats[distance:], data["artists"][order[distance:], order[:-distance]] / distance
        )
    monotony = 0.0
    if len(order) >= _MONOTONY_WINDOW:
        distances = data["body"][order[:-1], order[1:]]
        windows = np.convolve(distances, np.ones(_MONOTONY_WINDOW - 1) / (_MONOTONY_WINDOW - 1), mode="valid")
        monotony = float(np.maximum(0, 1 - windows / _MONOTONY_THRESHOLD).mean())
    return {
        "transition": float(data["transition"][order[:-1], order[1:]].mean()) if len(order) > 1 else 0.0,
        "repetition": float(repeats.mean()) if len(order) else 0.0,
        "monotony": monotony,
    }


def _order_cost(order: np.ndarray, data: dict[str, Any], profile: Profile) -> float:
    """Combine bounded terms using the chosen profile's fixed initial weights."""
    terms = _order_terms(order, data)
    return sum(
        terms[key] * weight
        for key, weight in zip(("transition", "repetition", "monotony"), _PROFILE_WEIGHTS[profile], strict=True)
    )


def _greedy_order(
    baseline: np.ndarray, free: np.ndarray, seed: int, data: dict[str, Any], profile: Profile
) -> np.ndarray:
    """Fill free slots using real adjacent boundaries and recent artist/texture history."""
    order = baseline.copy()
    remaining = np.zeros(len(order), dtype=bool)
    remaining[baseline[free]] = True
    free_set = set(free)
    transition_weight, repeat_weight, monotony_weight = _PROFILE_WEIGHTS[profile]
    for position in free:
        candidates = np.flatnonzero(remaining)
        if position == free[0]:
            chosen = seed
        else:
            scores = transition_weight * data["transition"][order[position - 1], candidates]
            if position + 1 < len(order) and position + 1 not in free_set:
                scores = scores + transition_weight * data["transition"][candidates, order[position + 1]]
            repeated = np.zeros(len(candidates))
            for distance in range(1, min(_ARTIST_WINDOW, position) + 1):
                repeated = np.maximum(repeated, data["artists"][candidates, order[position - distance]] / distance)
            scores = scores + repeat_weight * repeated
            if position >= _MONOTONY_WINDOW - 1:
                previous = order[position - (_MONOTONY_WINDOW - 1) : position]
                distances = data["body"][previous[:-1], previous[1:]].sum() + data["body"][previous[-1], candidates]
                scores = scores + monotony_weight * np.maximum(
                    0, 1 - distances / (_MONOTONY_WINDOW - 1) / _MONOTONY_THRESHOLD
                )
            chosen = int(candidates[np.argmin(scores)])
        order[position] = chosen
        remaining[chosen] = False
    return order


def _improve_order(
    candidate: tuple[np.ndarray, float], free: np.ndarray, data: dict[str, Any], profile: Profile, budget: int
) -> tuple[np.ndarray, float, int]:
    """Try swaps and both relocation directions, rescoring all affected directed terms."""
    best, cost, evaluated = candidate[0].copy(), candidate[1], 0
    for _ in range(2):
        improved = False
        for gap in range(1, len(free)):
            for first in range(len(free) - gap):
                last = first + gap
                operations = ("swap",) if gap == 1 else ("swap", "forward", "backward")
                for operation in operations:
                    if evaluated >= budget:
                        return best, cost, evaluated
                    trial = best.copy()
                    slots = free[first : last + 1]
                    if operation == "swap":
                        trial[slots[0]], trial[slots[-1]] = trial[slots[-1]], trial[slots[0]]
                    else:
                        trial[slots] = np.roll(trial[slots], -1 if operation == "forward" else 1)
                    trial_cost = _order_cost(trial, data, profile)
                    evaluated += 1
                    if trial_cost < cost - 1e-12:
                        best, cost, improved = trial, trial_cost, True
        if not improved:
            break
    return best, cost, evaluated


def _arrange(entries: list[dict[str, Any]], data: dict[str, Any] | None, choices: dict[str, Any]) -> dict[str, Any]:
    """Return the best bounded-search result, retaining the feasible original on ties."""
    baseline, free = _feasible_order(entries, choices["first_occurrence"], choices["last_occurrence"])
    best = baseline
    evaluations = 0
    baseline_cost = cost = None
    terms = None
    if data is not None:
        baseline_cost = cost = _order_cost(baseline, data, choices["profile"])
        evaluations = 1
        if len(free):
            starts = baseline[free][np.argsort(data["parts"]["summary"]["intensity"][baseline[free]], kind="stable")]
            for index in np.linspace(0, len(starts) - 1, min(4, len(starts)), dtype=int):
                candidate = _greedy_order(baseline, free, int(starts[index]), data, choices["profile"])
                candidate_cost = _order_cost(candidate, data, choices["profile"])
                evaluations += 1
                if candidate_cost < cost - 1e-12:
                    best, cost = candidate, candidate_cost
            best, cost, extra = _improve_order(
                (best, cost), free, data, choices["profile"], _MAX_EVALUATIONS - evaluations
            )
            evaluations += extra
        terms = _order_terms(best, data)
    return {
        **choices,
        "version": _SCORING_VERSION,
        "order": [entries[int(i)]["occurrence"] for i in best],
        "cost": cost,
        "baseline_cost": baseline_cost,
        "terms": terms,
        "evaluations": evaluations,
        "limited": data is None,
        "total_edges": max(0, len(entries) - 1),
        "assessed_edges": int(data["assessed"][best[:-1], best[1:]].sum()) if data is not None else None,
    }


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
        self.playlist_name: str | None = None
        self.original_items: list[dict[str, Any]] = []
        self.current_order: list[str] = []
        self.snapshot_id: str | None = None
        self.restore_order: list[str] = []
        self.audio_features: dict[str, dict[str, Any]] = {}
        self.youtube_cookies: str | None = None
        self.cached_count = 0
        self.recording_count = 0
        self.arrangement_data: dict[str, Any] | None = None
        self.arrangement_stamp: tuple[str, int] | None = None
        self.arrangement_results: dict[Profile, dict[str, Any]] = {}
        self.arrangement_result: dict[str, Any] = {}

    def _fetch_tracks_from_spotify(self) -> list[dict[str, Any]]:
        """Retain every occurrence and return catalog tracks eligible for analysis."""
        self.original_items = []
        self.restore_order = []
        self.arrangement_stamp = None
        self.arrangement_results.clear()
        self.arrangement_result = {}
        scope = f"{self.playlist_id}:{self.snapshot_id or secrets.token_urlsafe(16)}"
        results = self.sp.playlist_items(self.playlist_id)
        while results:
            for item in results["items"]:
                position = len(self.original_items)
                self.original_items.append(self._playlist_entry(item or {}, f"{scope}:{position}", position))
            results = self.sp.next(results) if results.get("next") else None
        self.current_order = [entry["occurrence"] for entry in self.original_items]
        return [entry for entry in self.original_items if entry["fixed_reason"] is None]

    @staticmethod
    def _playlist_entry(item: dict[str, Any], occurrence: str, position: int) -> dict[str, Any]:
        """Describe a playlist occurrence even when its recording is unavailable."""
        track = item.get("item") or item.get("track") or {}
        kind = track.get("type", "track")
        reason = None
        if track.get("is_local") or item.get("is_local"):
            kind, reason = "local", "Local file"
        elif not track.get("id") or track.get("is_playable") is False:
            kind, reason = "unavailable", "Unavailable on Spotify"
        elif kind != "track":
            reason = "Episode" if kind == "episode" else "Unsupported item"
        release_date = (track.get("album") or {}).get("release_date") or ""
        return {
            "occurrence": occurrence,
            "spotify_identity": SpotifyPlaylistSorter._item_identity(item),
            "original_position": position,
            "id": track.get("id"),
            "kind": kind,
            "fixed_reason": reason,
            "analysis_status": "fixed" if reason else "pending",
            "Track": track.get("name") or "Unavailable item",
            "Artist": ", ".join(a.get("name") or "Unknown artist" for a in track.get("artists") or [])
            or (track.get("show") or {}).get("publisher")
            or "",
            "artist_names": [a.get("name") or "" for a in track.get("artists") or []],
            "artist_ids": [a["id"] for a in track.get("artists") or [] if a.get("id")],
            "Popularity": track.get("popularity"),
            "duration_ms": track.get("duration_ms"),
            "release_year": release_date[:4],
            "album": (track.get("album") or {}).get("name") or "",
        }

    @staticmethod
    def _download_and_load(
        source: dict[str, Any],
        *,
        cookie_text: str = "",
        video_info: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, int]:
        """Retry a failed download once with fresh audio metadata, then allow another candidate."""
        last_error = SourceAccessError("download_failed")
        for attempt in range(2):
            if attempt:
                sleep(1)
            with tempfile.TemporaryDirectory() as directory:
                options: dict[str, Any] = {
                    **youtube_options(cookie_text),
                    "format": "bestaudio",
                    "check_formats": False,
                    "outtmpl": str(Path(directory) / "audio.%(ext)s"),
                    "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
                    "postprocessor_args": {"ffmpeg_o": ["-ar", "22050", "-ac", "1"]},
                }
                try:
                    with yt_dlp.YoutubeDL(options) as downloader:
                        video = (
                            video_info
                            if attempt == 0 and video_info is not None
                            else downloader.extract_info(source["url"], download=False)
                        )
                        if (
                            not video
                            or video.get("id") != source["id"]
                            or (metadata is not None and _select_recording(_rank_recordings([video], metadata)) is None)
                        ):
                            raise SourceAccessError("recording_changed")  # noqa: TRY301, EM101 - fixed reason code.
                        downloader.process_ie_result(video, download=True)
                    return load_audio(str(Path(directory) / "audio.wav"))
                except SourceAccessError:
                    raise
                except Exception as error:
                    reason = failure_reason(str(error)) or options["logger"].reason or "download_failed"
                    last_error = SourceAccessError(reason)
                    if reason in SHARED_FAILURES:
                        raise last_error from error
        raise last_error

    @staticmethod
    def _find_recordings(
        metadata: dict[str, Any], cookie_text: str, diagnostics: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        """Search cheaply, then validate a bounded set using full music metadata."""
        options: dict[str, Any] = {**youtube_options(cookie_text), "extract_flat": "in_playlist", "format": "bestaudio"}
        full: dict[str, dict[str, Any]] = {}
        with yt_dlp.YoutubeDL(options) as search:
            started = perf_counter()
            query = f"ytsearch10:{metadata['title']} {' '.join(metadata['artists'][:2])} audio"
            try:
                info = search.extract_info(query, download=False) or {}
            except Exception as error:
                raise SourceAccessError(
                    failure_reason(str(error)) or options["logger"].reason or "source_failed"
                ) from error
            diagnostics["search_seconds"] = round(perf_counter() - started, 3)
            entries = [entry for entry in (info.get("entries") or [info]) if entry]
            candidates = _shortlist(entries, metadata)
            diagnostics["search_results"] = len(entries)
            diagnostics["candidates_checked"] = 0
            started = perf_counter()
            last_error = None
            for candidate in candidates:
                diagnostics["candidates_checked"] += 1
                try:
                    options["logger"].reason = None
                    video = search.extract_info(f"https://www.youtube.com/watch?v={candidate['id']}", download=False)
                    if video and video.get("id") == candidate["id"]:
                        full[candidate["id"]] = video
                except Exception as error:
                    reason = failure_reason(str(error)) or options["logger"].reason or "source_failed"
                    if reason in SHARED_FAILURES:
                        raise SourceAccessError(reason) from error
                    last_error = SourceAccessError(reason)
            diagnostics["metadata_seconds"] = round(perf_counter() - started, 3)
            if not full and (last_error or options["logger"].reason):
                raise last_error or SourceAccessError(options["logger"].reason or "source_failed")
        return _rank_recordings(list(full.values()), metadata), full

    @staticmethod
    def _analyze_track(  # noqa: C901, PLR0911 - bounded retries and terminal progress outcomes.
        track: dict[str, Any], on_stage: Callable[[str], None] | None = None, *, cookie_text: str | None = None
    ) -> dict[str, Any]:
        """Resolve exact recording evidence and retain safe stage timings for diagnosis."""
        metadata = _metadata(track)
        notify = on_stage or (lambda _stage: None)
        started = perf_counter()
        diagnostics: dict[str, Any] = {}

        def finish(result: dict[str, Any]) -> dict[str, Any]:
            diagnostics["total_seconds"] = round(perf_counter() - started, 3)
            logger.info(
                "Recording %s: status=%s reason=%s timings=%s",
                track["id"],
                result["status"],
                result.get("reason"),
                diagnostics,
            )
            return {**result, "diagnostics": diagnostics}

        duration = _positive_number(metadata["duration_ms"])
        if duration is not None and duration > MAX_SECONDS * 1000:
            return finish({"status": "unsupported", "reason": "too_long", "message": "Longer than twenty minutes"})
        if duration is None or not metadata["artists"] or not all(metadata["artists"]):
            return finish(
                {
                    "status": "uncertain",
                    "reason": "missing_metadata",
                    "message": "Spotify recording details are missing",
                }
            )
        try:
            cookies = configured_cookies() if cookie_text is None else cookie_text
            notify("matching")
            ranked, full = SpotifyPlaylistSorter._find_recordings(metadata, cookies, diagnostics)
            failure = {"status": "uncertain", "reason": "no_match", "message": "No matching recording found"}
            while source := _select_recording(ranked):
                try:
                    notify("downloading")
                    step = perf_counter()
                    audio, sr = SpotifyPlaylistSorter._download_and_load(
                        source, cookie_text=cookies, video_info=full[source["id"]], metadata=metadata
                    )
                    diagnostics["download_seconds"] = round(perf_counter() - step, 3)
                    if abs(len(audio) / sr - source["duration"]) > max(3.0, source["duration"] * 0.02):
                        raise SourceAccessError("download_failed")  # noqa: TRY301, EM101 - fixed reason code.
                    notify("analyzing")
                    step = perf_counter()
                    analysis = analyze_audio(audio, sr)
                    diagnostics["analysis_seconds"] = round(perf_counter() - step, 3)
                    return finish(
                        {
                            "status": "ready",
                            "metadata": metadata,
                            "source": source,
                            "source_fingerprint": _source_fingerprint(source),
                            "analysis": analysis,
                        }
                    )
                except SourceAccessError as error:
                    if error.reason in SHARED_FAILURES:
                        return finish(error.result())
                    failure = error.result()
                    ranked.remove(source)
                except Exception:  # noqa: BLE001 - retain another independently eligible source as a fallback.
                    failure = SourceAccessError("analysis_failed").result()
                    ranked.remove(source)
            return finish(failure)
        except SourceAccessError as error:
            return finish(error.result())
        except Exception:  # noqa: BLE001 - do not expose extractor exceptions or URLs.
            return finish(SourceAccessError("source_failed").result())

    def _fetch_audio_features_local(  # noqa: C901, PLR0915 - cache checkpoints and shared-source failure handling.
        self,
        tracks: list[dict[str, Any]],
        progress_callback: Callable[[int, int], None] | None = None,
        record_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Share recording work across occurrences and checkpoint successful raw analyses."""
        cache = _load_cache()
        report_record = record_callback or (lambda _key, _result: None)
        report_progress = progress_callback or (lambda _done, _total: None)
        unique = {track["id"]: track for track in tracks}
        counts = Counter(track["id"] for track in tracks)
        results = {key: cache[key] for key, track in unique.items() if _cache_matches(cache.get(key), _metadata(track))}
        completed = sum(counts[key] for key in results)
        self.cached_count = completed
        self.recording_count = len(unique)
        for key, result in results.items():
            report_record(key, result)
        report_progress(completed, len(tracks))

        stopped = Event()
        shared_failure: dict[str, Any] = {}
        cookies = self.youtube_cookies
        if len(results) < len(unique) and cookies is None:
            try:
                cookies = configured_cookies()
            except SourceAccessError as error:
                shared_failure = error.result()
                stopped.set()

        def analyze_one(track: dict[str, Any]) -> dict[str, Any]:
            nonlocal shared_failure
            if stopped.is_set():
                return shared_failure.copy()
            kwargs: dict[str, Any] = {"cookie_text": cookies}
            if record_callback is not None:
                kwargs["on_stage"] = lambda stage: record_callback(track["id"], {"status": stage})
            result = self._analyze_track(track, **kwargs)
            if result.get("reason") in SHARED_FAILURES:
                shared_failure = result
                stopped.set()
            return result

        dirty = 0
        try:
            # ponytail: two full recordings in memory; use streaming decode if measured memory requires it.
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {
                    executor.submit(analyze_one, track): key for key, track in unique.items() if key not in results
                }
                for future in as_completed(futures):
                    key = futures[future]
                    try:
                        result = future.result()
                    except Exception:  # noqa: BLE001 - isolate failures from source and decoder plugins.
                        result = {
                            "status": "error",
                            "reason": "analysis_failed",
                            "message": "Couldn't analyze this song",
                        }
                    results[key] = result
                    report_record(key, result)
                    if result.get("status") == "ready":
                        cache[key] = result
                        dirty += 1
                        if dirty >= _CACHE_CHECKPOINT:
                            _save_cache(cache)
                            dirty = 0
                    completed += counts[key]
                    report_progress(completed, len(tracks))
        finally:
            if dirty:
                _save_cache(cache)
        return _with_intensity(results)

    def load_playlist(
        self,
        progress_callback: Callable[[int, int], None] | None = None,
        entries_callback: Callable[[list[dict[str, Any]]], None] | None = None,
        record_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> pd.DataFrame | None:
        """Load playlist name and track data using Spotify API + local audio analysis.

        Args:
            progress_callback: Optional callable ``(completed: int, total: int)``
                forwarded to the local audio-feature analysis step.
            entries_callback: Receives the complete metadata before audio work starts.
            record_callback: Receives recording stages and completed results.
        """
        logger.info("Loading playlist metadata for: %s", self.playlist_id)
        self.invalidate_save()
        try:
            playlist_info = self.sp.playlist(self.playlist_id, fields="name,snapshot_id")
            self.playlist_name = playlist_info["name"]
            self.snapshot_id = playlist_info["snapshot_id"]
            logger.info("Playlist Name (from Spotify): '%s'", self.playlist_name)
        except (spotipy.SpotifyException, KeyError, ValueError) as e:
            logger.warning("Failed to get playlist name from Spotify: %s. Will proceed without it.", e)
            self.playlist_name = f"Playlist {self.playlist_id}"

        spotify_tracks = self._fetch_tracks_from_spotify()
        if entries_callback is not None:
            entries_callback(self.original_items)
        audio_features = (
            self._fetch_audio_features_local(
                spotify_tracks, progress_callback=progress_callback, record_callback=record_callback
            )
            if spotify_tracks
            else {}
        )
        self.audio_features = audio_features
        for entry in self.original_items:
            features = audio_features.get(entry["id"], {}) if entry["fixed_reason"] is None else {}
            if entry["analysis_status"] != "fixed":
                entry["analysis_status"] = (
                    "fixed" if features.get("status") == "unsupported" else features.get("status", "error")
                )
            entry.update(
                BPM=features.get("tempo"),
                Energy=features.get("energy"),
                Camelot=features.get("camelot"),
            )
            if entry["fixed_reason"] is None and features.get("status") != "ready":
                entry["fixed_reason"] = features.get("message", "Couldn't analyze this song")
        self.tracks_data = pd.DataFrame(self.original_items)
        if not self.tracks_data.empty:
            self.tracks_data = self.tracks_data.set_index("occurrence", drop=False)
        return self.tracks_data

    def valid_order(self, order: list[str]) -> bool:
        """Require every loaded occurrence once and keep fixed entries in their slots."""
        original = [entry["occurrence"] for entry in self.original_items]
        return (
            bool(original)
            and Counter(order) == Counter(original)
            and all(
                order[index] == entry["occurrence"]
                for index, entry in enumerate(self.original_items)
                if entry["fixed_reason"] is not None
            )
        )

    def choice_error(
        self, first: str | None = None, last: str | None = None, profile: Profile = "smooth"
    ) -> str | None:
        """Reject foreign profiles or pins that conflict with complete-entry constraints."""
        if profile not in _PROFILE_WEIGHTS:
            return "Choose Smooth or More variety."
        return _pin_error(self.original_items, first, last)

    def sort_playlist(
        self, first_occurrence: str | None = None, last_occurrence: str | None = None, profile: Profile = "smooth"
    ) -> list[str]:
        """Arrange complete occurrences using cached directed measurements and optional endpoints."""
        if self.choice_error(first_occurrence, last_occurrence, profile):
            return []
        stamp = (ANALYSIS_VERSION, _SCORING_VERSION)
        if self.arrangement_stamp != stamp:
            # ponytail: cap quadratic pair matrices; larger playlists retain every entry in a feasible baseline.
            self.arrangement_data = (
                _prepare_arrangement(self.original_items, self.audio_features)
                if len(self.original_items) <= _MAX_MATRIX_ENTRIES
                else None
            )
            self.arrangement_results.clear()
            self.arrangement_stamp = stamp
        choices = {"profile": profile, "first_occurrence": first_occurrence, "last_occurrence": last_occurrence}
        result = self.arrangement_results.get(profile)
        if result is None or any(result[key] != value for key, value in choices.items()):
            result = _arrange(self.original_items, self.arrangement_data, choices)
            self.arrangement_results[profile] = result
        order = result["order"]
        if (
            not self.valid_order(order)
            or (first_occurrence and order[0] != first_occurrence)
            or (last_occurrence and order[-1] != last_occurrence)
        ):
            return []
        other = self.arrangement_results.get("variety" if profile == "smooth" else "smooth")
        comparable = other is not None and all(
            other[key] == choices[key] for key in ("first_occurrence", "last_occurrence")
        )
        self.arrangement_result = {
            **result,
            "unchanged": order == self.current_order,
            "same_as_other_profile": other["order"] == order if comparable else None,
        }
        return list(order)

    def compare_playlists(self, order: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Return complete original and proposed sequences without changing identities."""
        if self.tracks_data is None or not self.valid_order(order):
            return pd.DataFrame(), pd.DataFrame()
        return self.tracks_data.copy(), self.tracks_data.reindex(order)

    def get_transition_analysis(self, order: list[str]) -> list[dict[str, Any]]:
        """Expose actual outro/intro evidence, leaving unmeasured edges explicitly unassessed."""
        if not self.valid_order(order):
            return []
        identities = {entry["occurrence"]: index for index, entry in enumerate(self.original_items)}
        data = self.arrangement_data
        transitions = []
        for position in range(len(order) - 1):
            first, second = identities[order[position]], identities[order[position + 1]]
            measures: dict[str, Any] = {
                "bpm_diff": None,
                "energy_diff": None,
                "score": None,
                "components": dict.fromkeys(_COMPONENTS),
                "evidence": dict.fromkeys(_COMPONENTS, 0.0),
            }
            if data is not None and data["assessed"][first, second]:
                evidence = {key: float(data["evidence"][key][first, second]) for key in _COMPONENTS}
                measures.update(
                    components={key: float(data["components"][key][first, second]) for key in _COMPONENTS},
                    evidence=evidence,
                    score=1 - float(data["transition"][first, second]),
                    bpm_diff=abs(
                        float(data["parts"]["outro"]["raw"][first, 0]) - float(data["parts"]["intro"]["raw"][second, 0])
                    )
                    if evidence["tempo"] > 0
                    else None,
                    energy_diff=float(
                        data["parts"]["intro"]["intensity"][second] - data["parts"]["outro"]["intensity"][first]
                    )
                    if evidence["intensity"] > 0
                    else None,
                )
            transitions.append(
                {
                    "index": position + 1,
                    "track1_occurrence": order[position],
                    "track2_occurrence": order[position + 1],
                    "track1_name": self.original_items[first]["Track"],
                    "track2_name": self.original_items[second]["Track"],
                    **measures,
                }
            )
        return transitions

    def review_summary(self, order: list[str], transitions: list[dict[str, Any]]) -> dict[str, Any]:
        """Compare assessment coverage and select at most three supported listening notes."""
        review: dict[str, Any] = {
            "original_assessed": None,
            "suggested_assessed": None,
            "total_edges": max(0, len(order) - 1),
            "highlights": [],
        }
        data = self.arrangement_data
        if data is None or not self.valid_order(order):
            return review
        original = self.get_transition_analysis([entry["occurrence"] for entry in self.original_items])
        review["original_assessed"] = sum(transition["score"] is not None for transition in original)
        review["suggested_assessed"] = sum(transition["score"] is not None for transition in transitions)
        identities = {entry["occurrence"]: i for i, entry in enumerate(self.original_items)}
        positions = [identities[occurrence] for occurrence in order]
        movable = [i for i, entry in enumerate(self.original_items) if not entry["fixed_reason"]]
        notes = []
        for index, transition in enumerate(transitions):
            if transition["score"] is None:
                continue
            note = _audio_note(transition)
            next_entry = positions[index + 1]
            if not data["artists"][next_entry, movable].all():
                for distance in range(1, min(_ARTIST_WINDOW, index + 1) + 1):
                    if data["artists"][next_entry, positions[index + 1 - distance]]:
                        artist_note = (0.35 / distance, "An artist appears again nearby.")
                        if note is None or artist_note[0] > note[0]:
                            note = artist_note
                        break
            if note is not None:
                strength, message = note
                notes.append(
                    (
                        strength,
                        {
                            "index": transition["index"],
                            "text": message,
                            "track1_occurrence": transition["track1_occurrence"],
                            "track2_occurrence": transition["track2_occurrence"],
                            "track1_name": transition["track1_name"],
                            "track2_name": transition["track2_name"],
                        },
                    )
                )
        notes.sort(key=lambda item: (-item[0], item[1]["index"]))
        review["highlights"] = [note for _, note in notes[:3]]
        return review

    @staticmethod
    def _item_identity(item: dict[str, Any]) -> tuple[Any, ...]:
        """Compare provider identity and occurrence metadata, excluding mutable track details."""
        track = item.get("item") or item.get("track") or {}
        return (
            track.get("type", "track"),
            track.get("id"),
            track.get("uri"),
            bool(item.get("is_local") or track.get("is_local")),
            item.get("added_at"),
            (item.get("added_by") or {}).get("id"),
        )

    @property
    def can_restore(self) -> bool:
        """The last verified save can be undone while this job and snapshot survive."""
        return bool(self.snapshot_id and self.restore_order)

    def invalidate_save(self) -> None:
        """Require a fresh playlist check after an external or uncertain change."""
        self.snapshot_id = None
        self.restore_order = []

    def _order_matches(self, order: list[str]) -> bool:
        """Read every page between matching snapshots and compare the complete sequence."""
        if (
            not self.snapshot_id
            or self.sp.playlist(self.playlist_id, fields="snapshot_id")["snapshot_id"] != self.snapshot_id
        ):
            return False
        observed = []
        results = self.sp.playlist_items(self.playlist_id)
        while results:
            observed.extend(self._item_identity(item or {}) for item in results["items"])
            results = self.sp.next(results) if results.get("next") else None
        identities = {entry["occurrence"]: entry["spotify_identity"] for entry in self.original_items}
        latest = self.sp.playlist(self.playlist_id, fields="snapshot_id")["snapshot_id"]
        return latest == self.snapshot_id and observed == [identities[occurrence] for occurrence in order]

    def update_spotify_playlist(self, order: list[str]) -> tuple[bool, str]:
        """Apply the exact complete preview using range moves, never replacement."""
        if not self.snapshot_id or not self.valid_order(order) or Counter(self.current_order) != Counter(order):
            return False, "Check the playlist again before saving."
        first, last = self.arrangement_result.get("first_occurrence"), self.arrangement_result.get("last_occurrence")
        if (first is not None and order[0] != first) or (last is not None and order[-1] != last):
            return False, "Arrange the playlist again before saving."
        return self._write_order(order)

    def restore_spotify_playlist(self) -> tuple[bool, str]:
        """Undo only the most recent verified save, independently of new preview choices."""
        if not self.can_restore or not self.valid_order(self.restore_order):
            return False, "There is no previous order to restore in this session."
        return self._write_order(self.restore_order.copy(), restore=True)

    def _write_order(self, order: list[str], *, restore: bool = False) -> tuple[bool, str]:
        """Move once per request and confirm the result without replay or rollback."""
        previous = self.current_order.copy()
        current = self.current_order.copy()
        self.restore_order = []
        operation = "Restore" if restore else "Saving"
        unverified = f"{operation} couldn't be verified. Some songs may have moved. Check the playlist again."
        try:
            if not self._order_matches(current):
                self.invalidate_save()
                return False, "This playlist changed on Spotify. Check it again before saving or restoring."
            # ponytail: one request per moved song; batch adjacent moves if save time becomes a problem.
            for destination, occurrence in enumerate(order):
                source = current.index(occurrence)
                if source == destination:
                    continue
                result = self.sp.playlist_reorder_items(
                    self.playlist_id, source, destination, snapshot_id=self.snapshot_id
                )
                self.snapshot_id = result["snapshot_id"]
                if not isinstance(self.snapshot_id, str) or not self.snapshot_id:
                    self.invalidate_save()
                    return False, unverified
                current.insert(destination, current.pop(source))
            if not self._order_matches(order):
                self.invalidate_save()
                return False, unverified
        except Exception:
            logger.exception("Could not finish reordering playlist %s", self.playlist_id)
            self.invalidate_save()
            return False, f"{operation} stopped. Some songs may have moved. Check the playlist again."
        else:
            self.current_order = current
            self.restore_order = [] if restore else previous
            return True, "Previous order restored on Spotify." if restore else "Saved to Spotify."
