"""Recording-match resolution: find, verify, download and measure one recording."""

from __future__ import annotations

import copy
import logging
import os
import re
import tempfile
import unicodedata
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from difflib import SequenceMatcher
from itertools import pairwise
from pathlib import Path
from threading import Condition
from time import perf_counter, sleep
from typing import TYPE_CHECKING, Any

from api.analysis_store import RecordingAnalysis, _cached_record, _positive_number, _source_fingerprint
from api.audio_analysis import MAX_SECONDS, analyze_sections, load_audio, section_plan
from api.youtube import SHARED_FAILURES, SourceAccessError, YoutubeSource, failure_reason

if TYPE_CHECKING:
    from collections.abc import Callable

    import numpy as np


logger = logging.getLogger(__name__)
_MATCH_SCORE = 0.75
_STRUCTURED_TITLE_SIMILARITY = 0.85
_SHORTLIST_SIMILARITY = 0.65
_UNATTRIBUTED_PENALTY = 0.05
_EDITION_OMISSION_PENALTY = 0.10
_SHORTLIST_LIMIT = 3
_FALLBACK_SHORTLIST = 2
_DOWNLOAD_ATTEMPT_SECONDS = 15.0
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
_GENERIC_QUALIFIERS = {"version", "audio", "video", "song", "full", "lyric", "lyrics", "official"}
_SPELLING_FUZZ = 0.85
_RECALL_THRESHOLD = 0.75


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


def _strip_decorations(title: str) -> str:
    """Drop "from ..." tails, declared editions and artist credits before comparisons."""
    title = re.sub(r"\s*[-([]\s*from\s+.*", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*[-([]\s*(?:album version|original version|original mix)\b.*", "", title, flags=re.IGNORECASE)
    title = re.sub(r"[([]\s*(?:feat\.?|ft\.?|featuring)\s+[^)\]]+[)\]]", "", title, flags=re.IGNORECASE)
    return re.sub(r"\b(?:feat\.?|ft\.?|featuring)\s+[^([\-]*", "", title, flags=re.IGNORECASE)


def _title_text(title: str) -> str:
    """Normalize recording titles while retaining version qualifiers and genuine title words."""
    return _normalize_text(_strip_decorations(title))


def _edition_group(title: str) -> frozenset[str]:
    """All words of a title's trailing parenthetical or dash group, when it looks like an edition."""
    text = _strip_decorations(title)
    if paren := re.search(r"\(([^()]*)\)\s*$", text):
        return frozenset(_normalize_text(paren.group(1)).split())
    if " - " in text:
        tail = frozenset(_normalize_text(text.rsplit(" - ", 1)[-1]).split())
        if len(tail - _GENERIC_QUALIFIERS) == 1:  # single-word tails read as editions, not movie names
            return tail
    return frozenset[str]()


def _qualifier_tokens(title: str) -> frozenset[str]:
    """Edition words a recording claims in its trailing group; uploads must not silently drop them."""
    return frozenset(word for word in _edition_group(title) if word not in _GENERIC_QUALIFIERS)


def _base_tokens(title: str) -> list[str]:
    """Requested title words outside the edition group, for decoration-tolerant recall."""
    group = _edition_group(title)
    return [word for word in _normalize_text(title).split() if word not in group]


def _token_close(word: str, tokens: list[str]) -> bool:
    """Treat a requested word as present when an upload spells it nearly the same way."""
    return any(word == token or SequenceMatcher(None, word, token).ratio() >= _SPELLING_FUZZ for token in tokens)


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
    base = _base_tokens(metadata["title"])
    if base:
        if not entry.get("track") and f" {_title_text(' '.join(base))} " in f" {candidate} ":
            similarity = max(similarity, 0.94)
        # Decorated upload titles keep the requested words; measure word recall, not string distance.
        candidate_tokens = candidate.split()
        recall = sum(_token_close(word, candidate_tokens) for word in base) / len(base)
        if recall >= _RECALL_THRESHOLD:
            similarity = max(similarity, recall)
    return similarity


def _artist_present(artist: str, evidence: str) -> bool:
    """Match credited names and common official-channel spellings such as ACDCVEVO."""
    artist, evidence = _normalize_text(artist), _normalize_text(evidence)
    if f" {artist} " in f" {evidence} ":
        return True
    compact = artist.replace(" ", "")
    if evidence.replace(" ", "") in {compact, compact + "vevo", compact + "topic"}:
        return True
    # Separator variants such as K.K. normalize to separated letters; match squeezed adjacent tokens.
    return compact in {a + b for a, b in pairwise(evidence.split())}


def _duration_tolerance(seconds: float) -> float:
    """Allow modest upload padding for best-effort matches without accepting much longer cuts."""
    return max(3.0, min(25.0, seconds * 0.08))


def _shortlist(entries: list[dict[str, Any]], metadata: dict[str, Any]) -> list[dict[str, Any]]:
    """Filter flat search metadata before spending requests on at most five videos."""
    artists = [_normalize_text(artist) for artist in metadata["artists"]]
    expected = float(metadata["duration_ms"]) / 1000
    ranked: list[tuple[float, dict[str, Any]]] = []
    fallback: list[dict[str, Any]] = []
    chosen: set[str] = set()
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
            # Titles in other scripts often reveal plain names after hydration; keep them as fallbacks.
            fallback.append(entry)
            continue
        channel = _normalize_text(str(entry.get("channel") or entry.get("uploader") or ""))
        provenance = channel.endswith(" topic") or bool(entry.get("channel_is_verified"))
        ranked.append((similarity + 0.1 * provenance, entry))
    shortlist = [entry for _, entry in sorted(ranked, key=lambda item: -item[0])[:_SHORTLIST_LIMIT]]
    chosen.update(candidate["id"] for candidate in shortlist)
    # Uploads whose flat titles could not be scored still deserve hydration when time agrees.
    for entry in fallback:
        if len(shortlist) >= _SHORTLIST_LIMIT + _FALLBACK_SHORTLIST:
            break
        if str(entry.get("id")) not in chosen:
            chosen.add(str(entry["id"]))
            shortlist.append(entry)
    return shortlist


def _credit_introduces_strangers(artist_credits: list[str], artists: list[str]) -> bool:
    """Detect credited names the request never names, spelled differently or not at all."""
    for credited_artist in artist_credits:
        text = _normalize_text(str(credited_artist))
        if not text:
            continue
        if any(_artist_present(artist, " " + text + " ") for artist in artists):
            continue
        if max((SequenceMatcher(None, text, artist).ratio() for artist in artists), default=0.0) >= _SPELLING_FUZZ:
            continue
        return True
    return False


def _identity_conflicts(entry: dict[str, Any], artists: list[str], requested_title: str) -> bool:
    """Reject uploads whose credits, channel or claimed edition contradict the requested recording."""
    artist_credits = _credited_names(entry)
    credited = " " + _normalize_text(" ".join(artist_credits)) + " "
    channel_text = _normalize_text(str(entry.get("channel") or entry.get("uploader") or ""))
    # Structured credits can misspell or rename artists; the owning channel is independent evidence.
    if (
        credited.strip()
        and not any(_artist_present(artist, credited) for artist in artists)
        and not any(_artist_present(artist, channel_text) for artist in artists)
    ):
        return True
    # An upload claiming an edition the request never asked for is a different recording.
    claimed = _qualifier_tokens(str(entry.get("title") or ""))
    requested_text = _normalize_text(requested_title)
    return bool(claimed) and not claimed <= set(requested_text.split())


def _edition_missing(source_title: str, credited: str, album: str, requested_title: str) -> bool:
    """Check whether an upload silently drops the edition the request declares."""
    required = _qualifier_tokens(requested_title)
    carrier = _normalize_text(source_title + " " + credited + " " + album)
    return bool(required) and not required <= set(carrier.split())


def _credited_names(entry: dict[str, Any]) -> list[str]:
    """Read structured artist credits tolerantly, falling back to a single artist field."""
    names = entry.get("artists") or [entry.get("artist") or ""]
    if isinstance(names, str):
        names = [names]
    return [str(name) for name in names]


def _eligible_duration(entry: object, expected: float) -> float | None:
    """Validate a hydrated entry's shape, identity and timing before deeper comparisons."""
    if not isinstance(entry, dict) or not isinstance(entry.get("title"), str):
        return None
    source_id = entry.get("id", "")
    duration = _positive_number(entry.get("duration"))
    if not isinstance(source_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", source_id) or duration is None:
        return None
    if abs(duration - expected) > _duration_tolerance(expected):
        return None
    return duration


def _rank_key(item: dict[str, Any]) -> tuple[Any, ...]:
    """Order ranked recordings: full music metadata first, then score, verification, stable id."""
    return (
        -item["evidence"]["music_metadata"],
        -item["score"],
        -item["evidence"]["verified_channel"],
        item["id"],
    )


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
        duration = _eligible_duration(entry, expected)
        if duration is None:
            continue
        tolerance = _duration_tolerance(expected)
        difference = abs(duration - expected)
        source_title = entry["title"]
        candidate_title = _candidate_title(entry, artists)
        # Upload labels can contradict otherwise clean structured music metadata.
        upload_title = _candidate_title({"title": source_title}, artists)
        if _variants(candidate_title) != _variants(title) or _variants(upload_title) != _variants(title):
            continue
        source_id = str(entry.get("id") or "")
        artist_credits = _credited_names(entry)
        credited = " " + _normalize_text(" ".join(artist_credits)) + " "
        channel = str(entry.get("channel") or entry.get("uploader") or "")
        channel_text = _normalize_text(channel)
        if _identity_conflicts(entry, artists, metadata["title"]):
            continue
        # An unlabeled upload can still be the requested edition; strangers among its
        # credits (another singer's take) or a missing edition both argue against it.
        edition_missing = _edition_missing(source_title, credited, str(entry.get("album") or ""), metadata["title"])
        if edition_missing and _credit_introduces_strangers(artist_credits, artists):
            continue
        evidence = (
            " " + _normalize_text(source_title + " " + credited + " " + str(entry.get("uploader") or channel)) + " "
        )
        similarity = _title_similarity(entry, metadata)
        if entry.get("track") and similarity < _STRUCTURED_TITLE_SIMILARITY:
            continue
        artist_fraction = sum(
            _artist_present(artist, evidence) or _artist_present(artist, channel_text) for artist in artists
        ) / len(artists)
        score = 0.5 * similarity + 0.25 + 0.05 * artist_fraction + 0.2 * (1 - difference / tolerance)
        # Uploads without any artist evidence need a clearly stronger title to avoid same-name covers.
        if not artist_fraction and not entry.get("channel_is_verified"):
            score -= _UNATTRIBUTED_PENALTY
        if edition_missing:
            score -= _EDITION_OMISSION_PENALTY
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
            "channel": channel,
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
    return sorted(eligible.values(), key=_rank_key)


def _select_recording(ranked: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Use the best eligible recording even when several uploads have similar scores."""
    return ranked[0] if ranked and ranked[0]["score"] >= _MATCH_SCORE else None


class _WorkerScale:
    """Bound recording concurrency by machine capacity, download speed and YouTube feedback."""

    MAX_WORKERS = 4
    MIN_CPUS = 4
    MIN_MEMORY_GB = 2.0
    FALLBACK_MEMORY_GB = 4.0
    SLOW_DOWNLOAD_SECONDS = 15.0
    SUCCESSES_PER_GROWTH = 8

    def __init__(self) -> None:
        self.limit = self._machine_limit()
        self.target = min(2, self.limit)
        self.successes = 0
        self.recent: deque[float] = deque(maxlen=3)

    @staticmethod
    def _machine_limit() -> int:
        """Prefer four workers only when CPUs and memory can hold their in-flight recordings."""
        cpus = os.cpu_count() or 2
        try:
            memory = next(
                int(line.split()[1])
                for line in Path("/proc/meminfo").read_text().splitlines()
                if "MemAvailable" in line
            )
            memory_gb = memory / 1024 / 1024
        except (OSError, StopIteration, ValueError):
            memory_gb = _WorkerScale.FALLBACK_MEMORY_GB
        return (
            _WorkerScale.MAX_WORKERS if cpus >= _WorkerScale.MIN_CPUS and memory_gb >= _WorkerScale.MIN_MEMORY_GB else 2
        )

    def adjust(self, result: dict[str, Any]) -> None:
        """React to finished recordings: growth needs sustained fast successes, limits stop growth."""
        if result.get("reason") == "rate_limit":
            self.target = 1
            self.successes = 0
            self.recent.clear()
            return
        if result.get("status") != "ready":
            self.successes = 0
            return
        download_seconds = (result.get("diagnostics") or {}).get("download_seconds")
        if download_seconds is not None:
            self.recent.append(download_seconds)
        self.successes += 1
        throttled = any(second > self.SLOW_DOWNLOAD_SECONDS for second in self.recent)
        if self.successes >= self.SUCCESSES_PER_GROWTH and self.target < self.limit and not throttled:
            self.target += 1
            self.successes = 0


class _DynamicGate:
    """Admission control whose target concurrency can change while a job is running."""

    def __init__(self, target: int) -> None:
        self._condition = Condition()
        self._in_flight = 0
        self.target = target

    def __enter__(self) -> None:
        with self._condition:
            while self._in_flight >= self.target:
                self._condition.wait()
            self._in_flight += 1

    def __exit__(self, *_exc: object) -> None:
        with self._condition:
            self._in_flight -= 1
            self._condition.notify()


def _download_section(
    video: dict[str, Any],
    plan: tuple[str, float, float],
    duration: float,
    directory: Path,
    youtube: YoutubeSource,
) -> np.ndarray:
    """Download and decode one sampled window, failing incomplete audio loudly."""
    label, start, end = plan
    options: dict[str, Any] = {
        "format": "bestaudio",
        "check_formats": False,
        "outtmpl": str(directory / f"{label}.%(ext)s"),
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
        "postprocessor_args": {"ffmpeg_o": ["-ar", "22050", "-ac", "1"]},
    }
    if end - start < duration - 0.5:
        options["download_ranges"] = lambda _info, _ytdl, first=start, last=end: [
            {"start_time": first, "end_time": last}
        ]
        options["force_keyframes_at_cuts"] = True
    youtube.download(video, options)
    audio, sr = load_audio(str(directory / f"{label}.wav"))
    if abs(len(audio) / sr - (end - start)) > max(1.0, (end - start) * 0.05):
        raise SourceAccessError("download_failed")  # noqa: EM101 - fixed reason code.
    return audio


def _fresh_video(  # noqa: PLR0913 - one identity re-verification request.
    source: dict[str, Any],
    video_info: dict[str, Any] | None,
    attempt: int,
    *,
    verify: bool,
    metadata: dict[str, Any] | None,
    youtube: YoutubeSource,
) -> dict[str, Any]:
    """Return current video details, confirming identity and requested-recording eligibility."""
    video = video_info if attempt == 0 and video_info is not None else youtube.fresh(source["url"])
    if not video or video.get("id") != source["id"]:
        raise SourceAccessError("recording_changed")  # noqa: EM101 - fixed reason code.
    if verify and metadata is not None and _select_recording(_rank_recordings([video], metadata)) is None:
        raise SourceAccessError("recording_changed") from None  # noqa: EM101 - fixed reason code.
    return video


def _download_sections(
    source: dict[str, Any],
    *,
    video_info: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    verify: bool = True,
    youtube: YoutubeSource | None = None,
) -> list[tuple[str, float, float, np.ndarray]]:
    """Download sampled windows concurrently with a per-attempt deadline, retrying once with fresh metadata."""
    client = youtube or YoutubeSource()
    duration = float(source["duration"])
    plan = section_plan(duration)
    last_error = SourceAccessError("download_failed")
    for attempt in range(2):
        if attempt:
            sleep(1)
        sections: list[tuple[str, float, float, np.ndarray]] = []
        try:
            with tempfile.TemporaryDirectory() as directory:
                video = _fresh_video(source, video_info, attempt, verify=verify, metadata=metadata, youtube=client)
                executor = ThreadPoolExecutor(max_workers=len(plan))
                submitted: list[Future[np.ndarray]] = [
                    executor.submit(
                        _download_section,
                        copy.deepcopy(video),
                        plan_section,
                        duration,
                        Path(directory),
                        client,
                    )
                    for plan_section in plan
                ]
                deadline = perf_counter() + _DOWNLOAD_ATTEMPT_SECONDS
                try:
                    sections.extend(
                        (label, start, end, future.result(timeout=deadline - perf_counter()))
                        for (label, start, end), future in zip(plan, submitted, strict=True)
                    )
                except TimeoutError:
                    logger.warning(
                        "Download attempt exceeded %.0fs; retrying with fresh metadata", _DOWNLOAD_ATTEMPT_SECONDS
                    )
                    raise
                finally:
                    executor.shutdown(wait=False, cancel_futures=True)
        except SourceAccessError:
            raise
        except Exception as error:
            reason = failure_reason(str(error)) or "download_failed"
            last_error = SourceAccessError(reason)
            if reason in SHARED_FAILURES:
                raise last_error from error
        else:
            return sections
    raise last_error


def _search_entries(
    metadata: dict[str, Any], diagnostics: dict[str, Any], youtube: YoutubeSource
) -> list[dict[str, Any]]:
    """Run one bounded YouTube search, retrying plainly when the audio hint yields junk."""
    started = perf_counter()
    query = f"ytsearch10:{metadata['title']} {' '.join(metadata['artists'][:2])} audio"
    entries = youtube.search(query)
    diagnostics["search_seconds"] = round(perf_counter() - started, 3)
    if not _shortlist(entries, metadata):
        # Some queries return junk with the audio hint; retry plainly before giving up.
        entries = youtube.search(f"ytsearch10:{metadata['title']} {metadata['artists'][0]}")
    diagnostics["search_results"] = len(entries)
    return entries


def search_recordings(track: dict[str, Any], youtube: YoutubeSource | None = None) -> list[dict[str, Any]]:
    """Return flat YouTube candidates so a listener can choose this song's recording."""
    client = youtube or YoutubeSource()
    metadata = _metadata(track)
    duration_ms = _positive_number(metadata["duration_ms"])
    if duration_ms is None or not metadata["artists"] or not all(metadata["artists"]):
        return []
    diagnostics: dict[str, Any] = {}
    entries = _search_entries(metadata, diagnostics, client)
    suggested = {str(entry["id"]) for entry in _shortlist(entries, metadata)}
    candidates: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", str(entry.get("id") or "")):
            continue
        candidates.append(
            {
                "video_id": entry["id"],
                "title": str(entry.get("title") or ""),
                "channel": str(entry.get("channel") or entry.get("uploader") or ""),
                "duration_seconds": _positive_number(entry.get("duration")),
                "live": bool(entry.get("is_live")),
                "suggested": entry["id"] in suggested,
            }
        )
    candidates.sort(key=lambda item: (not item["suggested"], item["title"]))
    return candidates


def _find_recordings(
    metadata: dict[str, Any], diagnostics: dict[str, Any], youtube: YoutubeSource
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Search cheaply and hydrate only until one candidate already proves eligible."""
    entries = _search_entries(metadata, diagnostics, youtube)
    candidates = _shortlist(entries, metadata)
    full: dict[str, dict[str, Any]] = {}
    ranked: list[dict[str, Any]] = []
    diagnostics["candidates_checked"] = 0
    failure: SourceAccessError | None = None
    while candidates and not _select_recording(ranked):
        candidate = candidates.pop(0)
        diagnostics["candidates_checked"] += 1
        try:
            video = youtube.hydrate(str(candidate["id"]))
        except SourceAccessError as error:
            if error.reason in SHARED_FAILURES:
                raise
            failure = error
            if not candidates and not full:
                raise
            continue
        if video is not None:
            full[str(video["id"])] = video
            ranked = _rank_recordings(list(full.values()), metadata)
    if not full and failure is not None:
        raise failure
    return ranked, full, candidates


def hydrate_candidate(candidate: dict[str, Any], youtube: YoutubeSource | None = None) -> dict[str, Any] | None:
    """Fetch one candidate's full music metadata without re-requesting known failures."""
    try:
        return (youtube or YoutubeSource()).hydrate(str(candidate["id"]))
    except SourceAccessError as error:
        if error.reason in SHARED_FAILURES:
            raise
        return None


def measure_source(  # noqa: PLR0913 - one measurement request.
    source: dict[str, Any],
    video_info: dict[str, Any] | None,
    metadata: dict[str, Any],
    notify: Callable[[str], None],
    *,
    verify: bool = True,
    youtube: YoutubeSource | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, float]]:
    """Download sampled windows and measure them, or return the terminal failure result."""
    client = youtube or YoutubeSource()
    timings: dict[str, float] = {}
    try:
        notify("downloading")
        step = perf_counter()
        sections = _download_sections(source, video_info=video_info, metadata=metadata, verify=verify, youtube=client)
        timings["download_seconds"] = round(perf_counter() - step, 3)
        notify("analyzing")
        step = perf_counter()
        analysis = analyze_sections(sections)
        timings["analysis_seconds"] = round(perf_counter() - step, 3)
        record = record_for(source, metadata, analysis)
    except SourceAccessError as error:
        return None, error.result(), timings
    except Exception:  # noqa: BLE001 - retain another independently eligible source as a fallback.
        return None, SourceAccessError("analysis_failed").result(), timings
    return record, None, timings


def record_for(source: dict[str, Any], metadata: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    """Bind fresh metadata, a fingerprint and listener-facing recording details to validated measurements."""
    validated = RecordingAnalysis.model_validate(analysis)
    score = _positive_number(source.get("score"))
    return {
        "status": "ready",
        "metadata": metadata,
        "source": source,
        "source_fingerprint": _source_fingerprint(source),
        "analysis": validated.model_dump(),
        "recording": {
            "video_id": source.get("id"),
            "title": source.get("title"),
            "channel": source.get("channel"),
            "duration_seconds": source.get("duration"),
            "confident": score is not None and score >= _MATCH_SCORE,
        },
    }


def analyze_track(  # noqa: C901, PLR0911 - bounded retries and terminal progress outcomes.
    track: dict[str, Any],
    on_stage: Callable[[str], None] | None = None,
    *,
    cache: dict[str, dict[str, Any]] | None = None,
    video_analyses: dict[str, dict[str, Any]] | None = None,
    youtube: YoutubeSource | None = None,
) -> dict[str, Any]:
    """Resolve exact recording evidence and retain safe stage timings for diagnosis."""
    client = youtube or YoutubeSource()
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
        notify("matching")
        ranked, full, candidates = _find_recordings(metadata, diagnostics, client)
        failure = {"status": "uncertain", "reason": "no_match", "message": "No matching recording found"}

        def hydrate() -> bool:
            """Extend the ranked pool lazily; only failures force additional candidate requests."""
            while candidates and not _select_recording(ranked):
                candidate = candidates.pop(0)
                diagnostics["candidates_checked"] += 1
                video = hydrate_candidate(candidate, client)
                if video:
                    full[video["id"]] = video
                    ranked.extend(_rank_recordings([video], metadata))
                    ranked.sort(key=_rank_key)
            return bool(_select_recording(ranked))

        while hydrate():
            source = _select_recording(ranked)
            if source is None:  # pragma: no cover - hydrate() guarantees a source here.
                break
            if (cached := _cached_record(video_analyses or {}, source)) is not None:
                notify("analyzing")
                record = record_for(source, metadata, cached["analysis"])
                if cache is not None:
                    cache[track["id"]] = record
                return finish(record)
            record, next_failure, timings = measure_source(
                source, full.get(source["id"]), metadata, notify, youtube=client
            )
            diagnostics.update(timings)
            if record is not None:
                if cache is not None:
                    cache[track["id"]] = record
                if video_analyses is not None:
                    video_analyses[source["id"]] = record
                return finish(record)
            if next_failure and next_failure.get("reason") in SHARED_FAILURES:
                return finish(next_failure)
            failure = next_failure or failure
            ranked.remove(source)
        return finish(failure)
    except SourceAccessError as error:
        return finish(error.result())
    except Exception:  # noqa: BLE001 - do not expose extractor exceptions or URLs.
        return finish(SourceAccessError("source_failed").result())
