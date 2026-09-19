import type { Track } from "@/lib/api"

// One representation for "where does this fixed entry sit": the page keeps the
// chosen placements, and everything else (targets, overrides, conflicts) is
// derived here instead of being recomputed or passed back down as props.
export function placementTargets(
  fixedTracks: Track[],
  placements: Record<string, number>,
  total: number,
): Map<string, number> {
  const targets = new Map<string, number>()
  for (const track of fixedTracks)
    targets.set(
      track.occurrence,
      Math.min(
        Math.max(placements[track.occurrence] ?? track.original_position, 0),
        Math.max(total - 1, 0),
      ),
    )
  return targets
}

export function slotTaken(targets: Map<string, number>, occurrence: string, slot: number): boolean {
  for (const [key, value] of targets) if (key !== occurrence && value === slot) return true
  return false
}

export function fixedAtSlot(
  fixedTracks: Track[],
  placements: Record<string, number>,
  slot: number,
): Track | null {
  return (
    fixedTracks.find(
      (track) => (placements[track.occurrence] ?? track.original_position) === slot,
    ) ?? null
  )
}

// Only placements that differ from the entry's original position travel to the backend.
export function placementOverrides(
  fixedTracks: Track[],
  placements: Record<string, number>,
  total: number,
): Record<string, number> {
  const targets = placementTargets(fixedTracks, placements, total)
  const chosen: Record<string, number> = {}
  for (const track of fixedTracks) {
    const target = targets.get(track.occurrence) ?? 0
    if (target !== track.original_position) chosen[track.occurrence] = target
  }
  return chosen
}

export function placementsChanged(
  fixedTracks: Track[],
  placements: Record<string, number>,
  saved: Record<string, number>,
): boolean {
  return fixedTracks.some(
    (track) =>
      (placements[track.occurrence] ?? track.original_position) !==
      (saved[track.occurrence] ?? track.original_position),
  )
}

export function placementConflict(
  fixedTracks: Track[],
  placements: Record<string, number>,
  total: number,
  firstOccurrence: string | null,
  lastOccurrence: string | null,
): string | null {
  if (firstOccurrence !== null && firstOccurrence === lastOccurrence)
    return "Choose different entries for the first and last songs."
  const targets = placementTargets(fixedTracks, placements, total)
  for (const [occurrence, slot] of targets)
    for (const [other, otherSlot] of targets)
      if (occurrence !== other && slot === otherSlot)
        return "Two unanalyzable items claim the same position. Choose different positions."
  return null
}

export type PlacementChoice = "keep" | "top" | "bottom" | "custom"

// Translate one listener choice into the slot it claims; "keep" claims nothing.
export function resolvePlacement(
  choice: PlacementChoice,
  customPosition: number,
  total: number,
): number | null {
  if (choice === "top") return 0
  if (choice === "bottom") return total - 1
  if (choice === "custom") return Math.min(Math.max(customPosition, 1), Math.max(total, 1)) - 1
  return null
}
