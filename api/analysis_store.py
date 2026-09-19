"""The named recording-analysis record and its SQLite store."""

from __future__ import annotations

import hashlib
import json
import logging
import math
from typing import Any

import numpy as np
from pydantic import BaseModel, ValidationError

from api import store
from api.audio_analysis import ANALYSIS_VERSION, SETTINGS

logger = logging.getLogger(__name__)
_CACHE_SCHEMA = 2
_RESOLVER_VERSION = 3
_VIDEO_REUSE_SECONDS = 2.0


class SectionMeasurements(BaseModel):
    """One measured section of a recording with evidence for every claimed value."""

    start: float
    end: float
    rms_db: float | None
    onset: float | None
    tempo: float | None
    tempo_candidates: list[dict[str, float]]
    centroid: float | None
    contrast: list[float] | None
    chroma: list[float] | None
    camelot: str | None
    evidence: dict[str, float]


class RecordingAnalysis(BaseModel):
    """The named record one measured recording contributes: sections plus a playlist-comparable summary."""

    duration: float
    summary: SectionMeasurements
    intro: SectionMeasurements
    body: SectionMeasurements | None
    outro: SectionMeasurements


def _positive_number(value: object) -> float | None:
    """Reject missing, non-finite or non-positive source duration values."""
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result > 0 else None


def _source_fingerprint(source: dict[str, Any]) -> str:
    """Detect source-record changes before reusing their stored measurements."""
    return hashlib.sha256(json.dumps(source, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _header() -> dict[str, str]:
    """Describe the current analysis versions so stored records can be validated."""
    return {
        "schema": str(_CACHE_SCHEMA),
        "analysis_version": str(ANALYSIS_VERSION),
        "resolver_version": str(_RESOLVER_VERSION),
        "settings": json.dumps(SETTINGS, sort_keys=True),
    }


def _load_cache(track_ids: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """Load ready records for these track ids, resetting them when analysis versions change."""
    header = _header()
    stored = store.cache_meta()
    if stored is not None and stored != header:
        # Analysis versions changed: every stored record is invalid until re-measured.
        store.reset_cache(header, {})
        return {}
    return {key: json.loads(raw) for key, raw in store.cache_records(track_ids).items()}


def _save_cache(records: dict[str, dict[str, Any]]) -> None:
    """Checkpoint ready measurements so no analysis work is ever repeated after a crash."""
    store.save_cache_records({key: json.dumps(record) for key, record in records.items()})


def _cache_matches(record: object, metadata: dict[str, Any]) -> bool:
    """Require matching input metadata, complete validated measurements and unchanged source evidence."""
    if not isinstance(record, dict) or record.get("status") != "ready" or record.get("metadata") != metadata:
        return False
    source = record.get("source")
    analysis = record.get("analysis")
    if not isinstance(source, dict) or not isinstance(analysis, dict):
        return False
    try:
        validated = RecordingAnalysis.model_validate(analysis)
    except ValidationError:
        return False
    if validated.summary.rms_db is None or not math.isfinite(validated.summary.rms_db):
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
        quality = np.array(
            [
                [
                    r["analysis"]["summary"].get("evidence", {}).get("rms_db", 0.0),
                    r["analysis"]["summary"].get("evidence", {}).get("onset", 0.0),
                ]
                for r in ready.values()
            ],
            dtype=float,
        )
        normalized = np.full_like(values, 0.5)
        for column in range(values.shape[1]):
            valid = np.isfinite(values[:, column])
            if valid.any():
                low, high = np.percentile(values[valid, column], [5, 95])
                if high > low:
                    normalized[valid, column] = np.clip((values[valid, column] - low) / (high - low), 0, 1)
        # Treat unmeasured components as neutral, matching the arrangement's definition.
        energy = np.where(quality > 0, normalized, 0.5) @ np.array([0.6, 0.4])
        for (key, record), value in zip(ready.items(), energy, strict=True):
            summary = record["analysis"]["summary"]
            result[key] = {
                **record,
                "tempo": summary["tempo"],
                "camelot": summary["camelot"],
                "energy": float(value),
            }
    return result


def _video_index(cache: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index ready measurements by YouTube video so shared uploads are measured once."""
    index: dict[str, dict[str, Any]] = {}
    for record in cache.values():
        if record.get("status") == "ready" and isinstance(record.get("source"), dict):
            video_id = record["source"].get("id")
            if isinstance(video_id, str) and video_id not in index:
                index[video_id] = record
    return index


def _cached_record(video_analyses: dict[str, dict[str, Any]] | None, source: dict[str, Any]) -> dict[str, Any] | None:
    """Return a prior measurement for the same upload when its length still agrees."""
    cached = video_analyses.get(source["id"]) if video_analyses is not None else None
    cached_duration = _positive_number(cached["source"].get("duration")) if cached else None
    if (
        cached is not None
        and cached_duration is not None
        and abs(cached_duration - source["duration"]) <= _VIDEO_REUSE_SECONDS
    ):
        return cached
    return None
