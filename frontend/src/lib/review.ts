import type { Track } from "@/lib/api"

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
