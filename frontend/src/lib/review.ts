import type { Track } from "@/lib/api"

export type TimedTrack = {
  track: Track
  start: number
  end: number
  intensity: number | null
}

export function measuredIntensity(track: Track): number | null {
  const value = track.energy
  return track.analysis_status === "ready" &&
    track.fixed_reason === null &&
    value !== null &&
    Number.isFinite(value) &&
    value >= 0 &&
    value <= 1
    ? value
    : null
}

export function intensityLabel(value: number | null): string {
  if (value === null) return "Unavailable"
  if (value < 1 / 3) return "Lower"
  return value < 2 / 3 ? "Moderate" : "Higher"
}

export function elapsedTime(milliseconds: number): string {
  const seconds = Math.floor(milliseconds / 1000)
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor(seconds / 60) % 60
  const tail = String(seconds % 60).padStart(2, "0")
  return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${tail}` : `${minutes}:${tail}`
}

export function listeningTimeline(tracks: Track[]): TimedTrack[] | null {
  const result: TimedTrack[] = []
  let start = 0
  for (const track of tracks) {
    const duration = track.duration_ms
    if (
      duration === null ||
      !Number.isSafeInteger(duration) ||
      duration <= 0 ||
      !Number.isSafeInteger(start + duration)
    )
      return null
    result.push({ track, start, end: start + duration, intensity: measuredIntensity(track) })
    start += duration
  }
  return result
}

export function compareTimelines(original: Track[], suggested: Track[]) {
  const before = listeningTimeline(original)
  const after = listeningTimeline(suggested)
  const total = before?.at(-1)?.end
  if (!before?.length || !after?.length || total === undefined || total !== after.at(-1)?.end)
    return null
  const boundaries = [
    ...new Set([0, ...before.map((entry) => entry.end), ...after.map((entry) => entry.end)]),
  ].toSorted((a, b) => a - b)
  const points: { elapsed: number; original: number | null; suggested: number | null }[] = []
  let left = 0
  let right = 0
  for (const elapsed of boundaries) {
    // Keep the left and right values at each boundary so unknown spans stay gaps, not ramps.
    if (elapsed > 0)
      points.push({
        elapsed,
        original: before[left]?.intensity ?? null,
        suggested: after[right]?.intensity ?? null,
      })
    if (elapsed === total) break
    while (left < before.length - 1 && (before[left]?.end ?? total) <= elapsed) left++
    while (right < after.length - 1 && (after[right]?.end ?? total) <= elapsed) right++
    points.push({
      elapsed,
      original: before[left]?.intensity ?? null,
      suggested: after[right]?.intensity ?? null,
    })
  }
  return { original: before, suggested: after, total, points }
}
