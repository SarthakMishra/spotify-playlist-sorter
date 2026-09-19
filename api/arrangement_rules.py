"""Arrangement validity: complete permutations honoring fixed entries, pins and placements."""

from __future__ import annotations

from collections import Counter
from typing import Any


def identities(entries: list[dict[str, Any]]) -> dict[str, int]:
    """Map each loaded occurrence to its loaded position."""
    return {entry["occurrence"]: index for index, entry in enumerate(entries)}


def required_slot(entry: dict[str, Any], placements: dict[str, int] | None) -> int:
    """Return the slot a fixed entry must occupy in every valid order."""
    chosen = (placements or {}).get(entry["occurrence"])
    return int(entry["original_position"]) if chosen is None else chosen


def placement_targets(
    entries: list[dict[str, Any]], placements: dict[str, int] | None
) -> tuple[dict[str, int], str | None]:
    """Resolve the required slot for every fixed entry, rejecting invalid placement choices."""
    chosen = placements or {}
    targets: dict[str, int] = {}
    for entry in entries:
        if entry["fixed_reason"] is None:
            continue
        slot: int = required_slot(entry, chosen)
        if not 0 <= slot < len(entries):
            return {}, "Choose a position within the playlist."
        if slot in targets.values():
            return {}, "Choose a different position for each item."
        targets[entry["occurrence"]] = slot
    if placements is not None and any(occurrence not in targets for occurrence in placements):
        return {}, "Only items that cannot be analyzed can be placed."
    return targets, None


def endpoint_error(
    positions: dict[str, int], targets: dict[str, int], first: str | None, last: str | None, total: int
) -> str | None:
    """Reject pins that clash with placed unanalyzable entries."""
    for position, chosen in ((0, first), (total - 1, last)):
        if chosen is None:
            continue
        if chosen not in positions:
            return "Choose a song from this playlist."
        if chosen in targets and targets[chosen] != position:
            return "Choose a different position for this item or a different song."
        if chosen not in targets and position in targets.values():
            return "An item that cannot be analyzed already uses that position."
    return None


def pin_error(
    entries: list[dict[str, Any]], first: str | None, last: str | None, placements: dict[str, int] | None = None
) -> str | None:
    """Validate absolute endpoint and placement requirements against the loaded occurrences."""
    positions = identities(entries)
    if not entries or len(positions) != len(entries):
        return "Analyze the playlist again before arranging it."
    if first is not None and first == last:
        return "Choose different entries for the first and last songs."
    targets, error = placement_targets(entries, placements)
    if error:
        return error
    return endpoint_error(positions, targets, first, last, len(entries))


def order_valid(entries: list[dict[str, Any]], order: list[str], placements: dict[str, int] | None = None) -> bool:
    """Require every loaded occurrence once and keep fixed entries in their placed slots."""
    original = [entry["occurrence"] for entry in entries]
    return (
        bool(original)
        and Counter(order) == Counter(original)
        and all(
            order[required_slot(entry, placements)] == entry["occurrence"]
            for entry in entries
            if entry["fixed_reason"] is not None
        )
    )


def endpoints_satisfied(order: list[str], first: str | None, last: str | None) -> bool:
    """Require pinned first and last occurrences to occupy the ends of the order."""
    return (first is None or (bool(order) and order[0] == first)) and (
        last is None or (bool(order) and order[-1] == last)
    )
