import type { Options, Preset, Track } from "@/lib/api"

export type Preferences = Options

export const DEFAULT_PREFERENCES: Preferences = {
  preset: "steady",
  pace: 0.5,
  energy: 0.5,
  variety: 0.5,
}

export type PresetMeta = {
  value: Preset
  label: string
  description: string
  values: Pick<Preferences, "pace" | "energy" | "variety">
}

// Presets are named starting points; the sliders remain the real state so every
// choice stays adjustable without learning parameter names.
export const PRESETS: PresetMeta[] = [
  {
    value: "gentle",
    label: "Gentle flow",
    description: "Soft changes from song to song.",
    values: { pace: 0.5, energy: 0.5, variety: 0.2 },
  },
  {
    value: "steady",
    label: "Steady mix",
    description: "Balanced flow with room for variety.",
    values: { pace: 0.5, energy: 0.5, variety: 0.5 },
  },
  {
    value: "buildup",
    label: "Build up",
    description: "Starts calm and grows in intensity.",
    values: { pace: 0.5, energy: 0.85, variety: 0.4 },
  },
  {
    value: "mixed",
    label: "Mixed bag",
    description: "Space between similar songs and artists.",
    values: { pace: 0.5, energy: 0.5, variety: 0.85 },
  },
]

export type SliderMeta = {
  key: "pace" | "energy" | "variety"
  label: string
  low: string
  high: string
  hint: string
}

// Labels follow listener language: energy and mood words listeners rate reliably
// (Music Perception, 2026), pace described as slow/fast rather than BPM.
export const SLIDERS: SliderMeta[] = [
  {
    key: "pace",
    label: "Pace",
    low: "Slow songs first",
    high: "Fast songs first",
    hint: "Where the slower or quicker songs sit in your playlist.",
  },
  {
    key: "energy",
    label: "Energy",
    low: "Calm songs first",
    high: "Intense songs first",
    hint: "Where the calmer or more intense songs sit.",
  },
  {
    key: "variety",
    label: "Variety",
    low: "Similar songs together",
    high: "Spread out",
    hint: "How far apart repeated artists and similar sounds stay.",
  },
]

export function presetValues(preset: Preset): Pick<Preferences, "pace" | "energy" | "variety"> {
  return PRESETS.find((presetMeta) => presetMeta.value === preset)?.values ?? DEFAULT_PREFERENCES
}

const SLIDER_STATES: Record<
  "pace" | "energy" | "variety",
  Record<"low" | "high" | "balanced", string>
> = {
  pace: { low: "Slower songs lead", high: "Faster songs lead", balanced: "No strong preference" },
  energy: {
    low: "Calmer songs lead",
    high: "Intense songs lead",
    balanced: "No strong preference",
  },
  variety: {
    low: "Similar songs kept close",
    high: "Artists spread out",
    balanced: "Balanced spacing",
  },
}

export function describeSlider(key: "pace" | "energy" | "variety", value: number): string {
  const direction = value <= 0.45 ? "low" : value >= 0.55 ? "high" : "balanced"
  return SLIDER_STATES[key][direction]
}

function jitter(): number {
  return Math.round((Math.random() * 0.8 + 0.1) * 100) / 100
}

export function luckyPreferences(): Preferences {
  const picked = PRESETS[Math.floor(Math.random() * PRESETS.length)]
  const preset = picked ?? PRESETS[0]
  if (!preset) return DEFAULT_PREFERENCES
  return {
    preset: preset.value,
    pace: Math.random() < 0.55 ? 0.5 : jitter(),
    energy: Math.random() < 0.55 ? 0.5 : jitter(),
    variety:
      Math.round(
        Math.min(0.9, Math.max(0.1, preset.values.variety + (Math.random() - 0.5) * 0.3)) * 100,
      ) / 100,
  }
}

export function matchAttention(track: Track): "fix" | "check" | null {
  if (track.fixed_reason) return "fix"
  if (track.analysis_status === "ready" && track.recording && !track.recording.confident)
    return "check"
  return null
}
