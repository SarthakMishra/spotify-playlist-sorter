export type Session = {
  configured: boolean
  user: { id: string; name: string } | null
  csrf: string | null
}

export type Playlist = { id: string; name: string; total: number; image: string | null }
export type Profile = "smooth" | "variety"
export type Track = {
  occurrence: string
  original_position: number
  id: string | null
  duration_ms: number | null
  kind: string
  fixed_reason: string | null
  analysis_status:
    | "pending"
    | "matching"
    | "downloading"
    | "analyzing"
    | "ready"
    | "uncertain"
    | "error"
    | "fixed"
  name: string
  artist: string
  key: string | null
  bpm: number | null
  energy: number | null
}
export type Transition = {
  index: number
  track1_name: string
  track2_name: string
  track1_occurrence: string
  track2_occurrence: string
  bpm_diff: number | null
  energy_diff: number | null
  score: number | null
  components: Record<"tempo" | "intensity" | "texture" | "chroma", number | null>
  evidence: Record<"tempo" | "intensity" | "texture" | "chroma", number>
}
export type Job = {
  playlist_id: string
  revision: string
  name: string
  status:
    | "analyzing"
    | "ready"
    | "sorting"
    | "saving"
    | "saved"
    | "restoring"
    | "restored"
    | "error"
  can_restore: boolean
  completed: number
  total: number
  kept_count: number
  cached_count: number
  recording_count: number
  metadata_loaded: boolean
  analyzed_count: number
  profile: Profile
  first_occurrence: string | null
  last_occurrence: string | null
  arrangement: {
    version: number
    cost: number | null
    baseline_cost: number | null
    terms: { transition: number; repetition: number; monotony: number } | null
    evaluations: number
    assessed_edges: number | null
    total_edges: number
    limited: boolean
    unchanged: boolean
    same_as_other_profile: boolean | null
  } | null
  review: {
    original_assessed: number | null
    suggested_assessed: number | null
    total_edges: number
    highlights: {
      index: number
      text: string
      track1_occurrence: string
      track2_occurrence: string
      track1_name: string
      track2_name: string
    }[]
  } | null
  tracks: Track[]
  sorted_tracks: Track[]
  transitions: Transition[]
  error: string | null
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  headers.set("Accept", "application/json")
  if (options.body) headers.set("Content-Type", "application/json")
  const response = await fetch(`/api${path}`, { ...options, headers, credentials: "same-origin" })
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    const message =
      body && typeof body === "object" && "detail" in body && typeof body.detail === "string"
        ? body.detail
        : "We couldn't load this. Please try again."
    throw new ApiError(message, response.status)
  }
  // The backend validates these response models; JSON decoding is the one untyped transport boundary.
  // oxlint-disable-next-line typescript/no-unsafe-type-assertion -- Callers select the API's documented response model.
  return response.json() as Promise<T>
}

export function isWorking(job: Job | null) {
  return !!job && ["analyzing", "sorting", "saving", "restoring"].includes(job.status)
}

export type YouTubeAccess = {
  mode: "server" | "upload" | "anonymous"
  server_source: "file" | "browser" | "anonymous"
  browser: string | null
  node_available: boolean
  scripts_available: boolean
  yt_dlp_version: string
}
