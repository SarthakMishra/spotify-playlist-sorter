"""The per-session arranger: load a playlist, arrange it, then save or restore it."""

from __future__ import annotations

import logging
import secrets
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Event
from time import perf_counter
from typing import TYPE_CHECKING, Any

import spotipy

from api.analysis_store import _cache_matches, _load_cache, _save_cache, _video_index, _with_intensity
from api.arrangement_objective import (
    _ARTIST_WINDOW,
    _COMPONENTS,
    _MAX_MATRIX_ENTRIES,
    _SCORING_VERSION,
    _arrange,
    _audio_note,
    _normalized_options,
    _prepare_arrangement,
)
from api.arrangement_rules import endpoints_satisfied, identities, order_valid, pin_error
from api.audio_analysis import ANALYSIS_VERSION
from api.recording_match import (
    _DynamicGate,
    _metadata,
    _WorkerScale,
    analyze_track,
    hydrate_candidate,
    measure_source,
    search_recordings,
)
from api.youtube import SHARED_FAILURES

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

logger = logging.getLogger(__name__)
_CACHE_CHECKPOINT = 10


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
        self.playlist_name: str | None = None
        self.original_items: list[dict[str, Any]] = []
        self.current_order: list[str] = []
        self.placements: dict[str, int] = {}
        self.snapshot_id: str | None = None
        self.restore_order: list[str] = []
        self.audio_features: dict[str, dict[str, Any]] = {}
        self.cached_count = 0
        self.recording_count = 0
        self.arrangement_data: dict[str, Any] | None = None
        self.arrangement_stamp: tuple[str, int] | None = None
        self.arrangement_results: dict[tuple[Any, ...], dict[str, Any]] = {}
        self.arrangement_result: dict[str, Any] = {}

    @property
    def arrangement_summary(self) -> dict[str, Any]:
        """The listener-facing outcome of the current arrangement, independent of internal result fields."""
        return {"unchanged": self.arrangement_result["unchanged"], "limited": self.arrangement_result["limited"]}

    @property
    def movable_count(self) -> int:
        """How many loaded entries an arrangement may reorder."""
        return sum(entry["fixed_reason"] is None for entry in self.original_items)

    def _fetch_tracks_from_spotify(self) -> list[dict[str, Any]]:
        """Retain every occurrence and return catalog tracks eligible for analysis."""
        self.original_items = []
        self.restore_order = []
        self.placements = {}
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

    def _fetch_audio_features_local(  # noqa: C901, PLR0915 - cache checkpoints and shared-source failure handling.
        self,
        tracks: list[dict[str, Any]],
        progress_callback: Callable[[int, int], None] | None = None,
        record_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Share recording work across occurrences and checkpoint successful raw analyses."""
        unique = {track["id"]: track for track in tracks}
        cache = _load_cache(list(unique))
        report_record = record_callback or (lambda _key, _result: None)
        report_progress = progress_callback or (lambda _done, _total: None)
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

        videos = _video_index(cache)
        scale = _WorkerScale()
        gate = _DynamicGate(scale.target)

        def analyze_one(track: dict[str, Any]) -> dict[str, Any]:
            nonlocal shared_failure
            if stopped.is_set():
                return shared_failure.copy()
            kwargs: dict[str, Any] = {"cache": cache, "video_analyses": videos}
            if record_callback is not None:
                kwargs["on_stage"] = lambda stage: record_callback(track["id"], {"status": stage})
            with gate:
                result = analyze_track(track, **kwargs)
            if result.get("reason") in SHARED_FAILURES:
                shared_failure = result
                stopped.set()
            return result

        pending: dict[str, dict[str, Any]] = {}
        try:
            # ponytail: several sampled windows per worker stay small; measure memory before raising limits.
            with ThreadPoolExecutor(max_workers=scale.limit) as executor:
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
                    scale.adjust(result)
                    gate.target = scale.target
                    if result.get("status") == "ready":
                        cache[key] = result
                        pending[key] = result
                        if len(pending) >= _CACHE_CHECKPOINT:
                            _save_cache(pending)
                            pending.clear()
                    completed += counts[key]
                    report_progress(completed, len(tracks))
        finally:
            if pending:
                _save_cache(pending)
        return _with_intensity(results)

    def reanalyze_track(
        self,
        entry: dict[str, Any],
        video_id: str,
        record_callback: Callable[[str, dict[str, Any]], None] | None = None,
        deadline: float | None = None,
    ) -> tuple[bool, str]:
        """Reanalyze one occurrence with a listener-chosen recording and update cached state."""

        def expired() -> bool:
            return deadline is not None and perf_counter() > deadline

        if entry["id"] is None:
            return False, "This item has no Spotify recording to replace."
        notify = record_callback or (lambda _key, _result: None)
        notify(entry["id"], {"status": "matching"})
        video = hydrate_candidate({"id": video_id})
        if video is None or video.get("id") != video_id:
            return False, "Couldn't load that recording. Try another one."
        if expired():
            return False, "This took too long. Try again shortly."
        metadata = _metadata(entry)
        record, failure, _timings = measure_source(
            video, video, metadata, lambda stage: notify(entry["id"], {"status": stage}), verify=False
        )
        if record is None:
            return False, str(
                failure.get("message") or "Couldn't analyze this recording."
            ) if failure else "Couldn't analyze this recording."
        if expired():
            return False, "This took too long. Try again shortly."
        _save_cache({entry["id"]: record})
        processed = _with_intensity({**self.audio_features, entry["id"]: record})
        self.audio_features = processed
        features = processed.get(entry["id"], {})
        entry["analysis_status"] = "ready"
        entry["fixed_reason"] = None
        entry.update(BPM=features.get("tempo"), Energy=features.get("energy"), Camelot=features.get("camelot"))
        entry["Recording"] = features.get("recording")
        self.arrangement_data = None
        self.arrangement_stamp = None
        self.arrangement_results.clear()
        self.arrangement_result = {}
        # Spotify's order is untouched by a re-measurement; the save-time readback
        # still verifies the live snapshot, so the next save needs no re-analysis.
        notify(entry["id"], {"status": "ready"})
        return True, "Recording updated."

    def load_playlist(
        self,
        progress_callback: Callable[[int, int], None] | None = None,
        entries_callback: Callable[[list[dict[str, Any]]], None] | None = None,
        record_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> list[dict[str, Any]]:
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
                Recording=features.get("recording"),
            )
            if entry["fixed_reason"] is None and features.get("status") != "ready":
                entry["fixed_reason"] = features.get("message", "Couldn't analyze this song")
        return self.original_items

    def valid_order(self, order: list[str]) -> bool:
        """Require every loaded occurrence once and keep fixed entries in their placed slots."""
        return order_valid(self.original_items, order, self.placements)

    def choice_error(
        self, first: str | None = None, last: str | None = None, placements: dict[str, int] | None = None
    ) -> str | None:
        """Reject pins that conflict with complete-entry constraints."""
        return pin_error(self.original_items, first, last, placements)

    def save_problem(self, order: list[str], preview: list[str]) -> str | None:
        """Return why this order cannot be saved yet: invalid arrangement, stale preview or unchanged order."""
        if not self.valid_order(order) or order != preview or order == self.current_order:
            return "Review the playlist preview before saving."
        return None

    def search_recordings(self, track: dict[str, Any]) -> list[dict[str, Any]]:
        """Return flat YouTube candidates so a listener can choose this song's recording."""
        return search_recordings(track)

    def sort_playlist(
        self,
        options: Mapping[str, Any] | None = None,
        first_occurrence: str | None = None,
        last_occurrence: str | None = None,
        placements: dict[str, int] | None = None,
    ) -> list[str]:
        """Arrange complete occurrences using cached directed measurements and optional endpoints."""
        chosen_placements = dict(placements or {})
        chosen_options = _normalized_options(options)
        if self.choice_error(first_occurrence, last_occurrence, chosen_placements):
            return []
        self.placements = chosen_placements
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
        choices = {
            "options": chosen_options,
            "first_occurrence": first_occurrence,
            "last_occurrence": last_occurrence,
            "placements": chosen_placements,
        }
        key = (
            chosen_options["preset"],
            f"{chosen_options['pace']:.3f}",
            f"{chosen_options['energy']:.3f}",
            f"{chosen_options['variety']:.3f}",
            first_occurrence or "",
            last_occurrence or "",
            tuple(sorted(chosen_placements.items())),
        )
        result = self.arrangement_results.get(key)
        if result is None:
            result = _arrange(self.original_items, self.arrangement_data, choices)
            self.arrangement_results[key] = result
        order = result["order"]
        if not self.valid_order(order) or not endpoints_satisfied(order, first_occurrence, last_occurrence):
            return []
        self.arrangement_result = {
            **result,
            "unchanged": order == self.current_order,
        }
        return list(order)

    def proposed_tracks(self, order: list[str]) -> list[dict[str, Any]]:
        """Return the proposed sequence as complete entries, without changing identities."""
        if not self.valid_order(order):
            return []
        entries = {entry["occurrence"]: entry for entry in self.original_items}
        return [entries[occurrence] for occurrence in order]

    def get_transition_analysis(self, order: list[str]) -> list[dict[str, Any]]:
        """Expose actual outro/intro evidence, leaving unmeasured edges explicitly unassessed."""
        if not self.valid_order(order):
            return []
        positions = identities(self.original_items)
        data = self.arrangement_data
        transitions = []
        for position in range(len(order) - 1):
            first, second = positions[order[position]], positions[order[position + 1]]
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
        positions = [identities(self.original_items)[occurrence] for occurrence in order]
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

    def _read_snapshot(self) -> str | None:
        """Return the snapshot id Spotify currently reports for the playlist."""
        snapshot = self.sp.playlist(self.playlist_id, fields="snapshot_id")
        reported = snapshot.get("snapshot_id") if snapshot else None
        return reported if isinstance(reported, str) else None

    def _read_identities(self) -> list[tuple[Any, ...]]:
        """Read every page and list item identities in current playlist order."""
        observed = []
        results = self.sp.playlist_items(self.playlist_id)
        while results:
            observed.extend(self._item_identity(item or {}) for item in results["items"])
            results = self.sp.next(results) if results.get("next") else None
        return observed

    def _expected_identities(self, order: list[str]) -> list[tuple[Any, ...]]:
        """Translate an occurrence order into identities recorded when the playlist loaded."""
        identities_map = {entry["occurrence"]: entry["spotify_identity"] for entry in self.original_items}
        return [identities_map[occurrence] for occurrence in order]

    def _log_mismatch(self, phase: str, observed: list[tuple[Any, ...]], expected: list[tuple[Any, ...]]) -> None:
        """Point at the first differing position without logging track details."""
        detail = f"{len(observed)} items instead of {len(expected)}"
        if len(observed) == len(expected):
            for position, (seen, wanted) in enumerate(zip(observed, expected, strict=True)):
                if seen != wanted:
                    detail = f"position {position} differs"
                    break
        logger.warning("Playlist %s item readback %s does not match the write (%s)", self.playlist_id, phase, detail)

    def _order_matches(self, order: list[str]) -> bool:
        """Require an unchanged snapshot around a complete readback before writing."""
        if not self.snapshot_id or self._read_snapshot() != self.snapshot_id:
            logger.info("Playlist %s snapshot is missing or stale before the write", self.playlist_id)
            return False
        expected = self._expected_identities(order)
        observed = self._read_identities()
        if self._read_snapshot() != self.snapshot_id:
            logger.warning("Playlist %s snapshot moved while reading items before the write", self.playlist_id)
            return False
        if observed != expected:
            self._log_mismatch("before writing", observed, expected)
            return False
        return True

    def _confirm_order(self, order: list[str]) -> bool:
        """Trust the item readback over snapshots Spotify may echo or update late after a write."""
        expected = self._expected_identities(order)
        observed = self._read_identities()
        if observed != expected:
            self._log_mismatch("after writing", observed, expected)
            return False
        fresh = self._read_snapshot()
        if fresh:
            self.snapshot_id = fresh
        else:
            logger.warning("Playlist %s readback matched but Spotify reported no snapshot id", self.playlist_id)
        return True

    def update_spotify_playlist(self, order: list[str]) -> tuple[bool, str]:
        """Apply the exact complete preview using range moves, never replacement."""
        if not self.snapshot_id or not self.valid_order(order):
            return False, "Analyze the playlist again before saving."
        if not endpoints_satisfied(
            order,
            self.arrangement_result.get("first_occurrence"),
            self.arrangement_result.get("last_occurrence"),
        ):
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
        unverified = f"{operation} couldn't be verified. Some songs may have moved. Analyze the playlist again."
        try:
            if not self._order_matches(current):
                self.invalidate_save()
                return False, "This playlist changed on Spotify. Analyze it again before saving or restoring."
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
                    logger.warning(
                        "Playlist %s move to position %s returned no snapshot id", self.playlist_id, destination
                    )
                    self.invalidate_save()
                    return False, unverified
                current.insert(destination, current.pop(source))
            if not self._confirm_order(order):
                self.invalidate_save()
                return False, unverified
        except Exception:
            logger.exception("Could not finish reordering playlist %s", self.playlist_id)
            self.invalidate_save()
            return False, f"{operation} stopped. Some songs may have moved. Analyze the playlist again."
        else:
            self.current_order = current
            self.restore_order = [] if restore else previous
            return True, "Previous order restored on Spotify." if restore else "Saved to Spotify."
