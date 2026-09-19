"""The arrangement objective: pair measurements, cost terms and bounded search."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from api.arrangement_rules import identities, required_slot
from api.recording_match import _normalize_text

if TYPE_CHECKING:
    from collections.abc import Mapping

# (transition, repetition, monotony) base weights per named flow preset.
_PRESET_WEIGHTS: dict[str, tuple[float, float, float]] = {
    "gentle": (0.85, 0.08, 0.07),
    "steady": (0.70, 0.20, 0.10),
    "buildup": (0.70, 0.15, 0.15),
    "mixed": (0.55, 0.30, 0.15),
}
_ORDER_TERMS = ("transition", "repetition", "monotony", "pace", "energy")
_TILT_EPSILON = 1e-9
_TILT_STRENGTH = 0.5
_TILT_FRACTION = 0.35
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


def _feasible_order(
    entries: list[dict[str, Any]],
    first: str | None,
    last: str | None,
    placements: dict[str, int] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Place endpoints and fill remaining movable slots in their original relative order."""
    positions = identities(entries)
    locked = {required_slot(entry, placements): index for index, entry in enumerate(entries) if entry["fixed_reason"]}
    for position, chosen in ((0, first), (len(entries) - 1, last)):
        if chosen is not None:
            locked[position] = positions[chosen]
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

    def tilt_values(feature: str) -> np.ndarray:
        """Center a summary feature so ordering sliders can tilt where it sits in the order."""
        if feature == "tempo":
            raw, quality = parts["summary"]["raw"][:, 0], parts["summary"]["quality"][:, 0]
            valid = (quality > 0) & np.isfinite(raw) & (raw > 0)
            measured = np.log2(np.where(valid, raw, 1.0))[valid]
        else:
            raw, quality = parts["summary"]["intensity"], parts["summary"]["intensity_quality"]
            valid = (quality > 0) & np.isfinite(raw)
            measured = raw[valid]
        values = np.zeros(len(entries))
        if measured.size > 1 and measured.std() > _TILT_EPSILON:
            values[valid] = (measured - measured.mean()) / measured.std() * quality[valid]
        return values

    return {
        "parts": parts,
        "components": components,
        "evidence": evidence,
        "artists": shared,
        "transition": np.where(assessed, transition, 0.5),
        "body": (body["tempo"] + body["intensity"] + body["texture"]) / 3,
        "assessed": assessed,
        "pace_values": tilt_values("tempo"),
        "energy_values": tilt_values("energy"),
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
    fractions = np.linspace(0, 1, len(order)) if len(order) > 1 else np.zeros(len(order))
    return {
        "transition": float(data["transition"][order[:-1], order[1:]].mean()) if len(order) > 1 else 0.0,
        "repetition": float(repeats.mean()) if len(order) else 0.0,
        "monotony": monotony,
        "pace": float((fractions * data["pace_values"][order]).mean()) if len(order) else 0.0,
        "energy": float((fractions * data["energy_values"][order]).mean()) if len(order) else 0.0,
    }


def _normalized_options(options: Mapping[str, Any] | None) -> dict[str, Any]:
    """Validate listening options, keeping only recognized presets and bounded sliders."""
    raw = options or {}

    def slider(name: str) -> float:
        value = raw.get(name, 0.5)
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.5
        return number if 0.0 <= number <= 1.0 else 0.5

    return {
        "preset": raw.get("preset") if raw.get("preset") in _PRESET_WEIGHTS else "steady",
        "pace": slider("pace"),
        "energy": slider("energy"),
        "variety": slider("variety"),
    }


def _option_weights(options: Mapping[str, Any]) -> tuple[float, float, float, float, float]:
    """Translate listening options into cost weights for every ordered term."""
    transition, _, monotony = _PRESET_WEIGHTS.get(options.get("preset") or "", _PRESET_WEIGHTS["steady"])
    variety = float(options.get("variety", 0.5))
    return (
        transition,
        _TILT_FRACTION * (0.15 + 1.85 * variety),
        monotony * (0.75 + 0.5 * variety),
        (float(options.get("pace", 0.5)) - 0.5) * _TILT_STRENGTH,
        (float(options.get("energy", 0.5)) - 0.5) * _TILT_STRENGTH,
    )


def _order_cost(order: np.ndarray, data: dict[str, Any], weights: tuple[float, ...]) -> float:
    """Combine bounded terms using the chosen listening weights."""
    terms = _order_terms(order, data)
    return sum(terms[key] * weight for key, weight in zip(_ORDER_TERMS, weights, strict=True))


def _greedy_order(
    baseline: np.ndarray, free: np.ndarray, seed: int, data: dict[str, Any], weights: tuple[float, ...]
) -> np.ndarray:
    """Fill free slots using real adjacent boundaries and recent artist/texture history."""
    order = baseline.copy()
    remaining = np.zeros(len(order), dtype=bool)
    remaining[baseline[free]] = True
    free_set = set(free)
    transition_weight, repeat_weight, monotony_weight, pace_weight, energy_weight = weights
    span = max(1, len(order) - 1)
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
            fraction = position / span
            scores = (
                scores
                + (pace_weight * data["pace_values"][candidates] + energy_weight * data["energy_values"][candidates])
                * fraction
            )
            chosen = int(candidates[np.argmin(scores)])
        order[position] = chosen
        remaining[chosen] = False
    return order


def _improve_order(
    candidate: tuple[np.ndarray, float], free: np.ndarray, data: dict[str, Any], weights: tuple[float, ...], budget: int
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
                    trial_cost = _order_cost(trial, data, weights)
                    evaluated += 1
                    if trial_cost < cost - 1e-12:
                        best, cost, improved = trial, trial_cost, True
        if not improved:
            break
    return best, cost, evaluated


def _arrange(entries: list[dict[str, Any]], data: dict[str, Any] | None, choices: dict[str, Any]) -> dict[str, Any]:
    """Return the best bounded-search result, retaining the feasible original on ties."""
    baseline, free = _feasible_order(
        entries, choices["first_occurrence"], choices["last_occurrence"], choices.get("placements")
    )
    best = baseline
    evaluations = 0
    baseline_cost = cost = None
    terms = None
    weights = _option_weights(choices["options"])
    if data is not None:
        baseline_cost = cost = _order_cost(baseline, data, weights)
        evaluations = 1
        if len(free):
            starts = baseline[free][np.argsort(data["parts"]["summary"]["intensity"][baseline[free]], kind="stable")]
            for index in np.linspace(0, len(starts) - 1, min(4, len(starts)), dtype=int):
                candidate = _greedy_order(baseline, free, int(starts[index]), data, weights)
                candidate_cost = _order_cost(candidate, data, weights)
                evaluations += 1
                if candidate_cost < cost - 1e-12:
                    best, cost = candidate, candidate_cost
            best, cost, extra = _improve_order((best, cost), free, data, weights, _MAX_EVALUATIONS - evaluations)
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
