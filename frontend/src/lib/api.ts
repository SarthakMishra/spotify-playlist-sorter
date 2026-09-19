export type Session = {
  configured: boolean
  user: { id: string; name: string } | null
  csrf: string | null
}

export type Playlist = { id: string; name: string; total: number; image: string | null }
export type Preset = "gentle" | "steady" | "buildup" | "mixed"
export type Options = { preset: Preset; pace: number; energy: number; variety: number }
export type Recording = {
  video_id: string
  title: string | null
  channel: string | null
  duration_seconds: number | null
  confident: boolean
}
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
  recording: Recording | null
}
export type Candidate = {
  video_id: string
  title: string
  channel: string
  duration_seconds: number | null
  live: boolean
  suggested: boolean
}
export type ReviewHighlight = NonNullable<Job["review"]>["highlights"][number]
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
  metadata_loaded: boolean
  analyzed_count: number
  queue_position: number | null
  stale: boolean
  rematching: boolean
  /** Served from the analysis store: true results, but no live playlist data to act on. */
  stored: boolean
  options: Options
  first_occurrence: string | null
  last_occurrence: string | null
  placements: Record<string, number>
  arrangement: {
    unchanged: boolean
    limited: boolean
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
  error: string | null
}
export type QueueEntry = {
  playlist_id: string
  name: string
  status: "queued" | "running"
  queue_position: number | null
  completed: number
  total: number
  eta_seconds: number | null
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

// The session hands the browser one CSRF token per login; the client keeps it
// so mutating call sites never assemble auth headers themselves.
let csrfToken: string | null = null

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
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

function mutating(options: RequestInit): RequestInit {
  const headers = new Headers(options.headers)
  headers.set("X-CSRF-Token", csrfToken ?? "")
  return { ...options, headers }
}

export type SortRequest = {
  revision: string
  options: Options
  first_occurrence: string | null
  last_occurrence: string | null
  placements: Record<string, number>
}

export async function getSession(options: RequestInit = {}): Promise<Session> {
  const session = await request<Session>("/session", options)
  csrfToken = session.csrf
  return session
}

export function getPlaylists(options: RequestInit = {}): Promise<Playlist[]> {
  return request<Playlist[]>("/playlists", options)
}

export function getPreferences(options: RequestInit = {}): Promise<Options> {
  return request<Options>("/preferences", options)
}

export function savePreferences(preferences: Options, options: RequestInit = {}): Promise<Options> {
  return request<Options>("/preferences", {
    ...mutating(options),
    method: "PUT",
    body: JSON.stringify(preferences),
  })
}

export function getJob(playlistId: string, options: RequestInit = {}): Promise<Job | null> {
  return request<Job | null>(`/job/${playlistId}`, options)
}

export function getQueue(options: RequestInit = {}): Promise<QueueEntry[]> {
  return request<QueueEntry[]>("/queue", options)
}

export function analyzePlaylist(playlistId: string, options: RequestInit = {}): Promise<Job> {
  return request<Job>(`/playlists/${playlistId}/analyze`, { ...mutating(options), method: "POST" })
}

export function sortPreview(
  playlistId: string,
  body: SortRequest,
  options: RequestInit = {},
): Promise<Job> {
  return request<Job>(`/job/${playlistId}/sort`, {
    ...mutating(options),
    method: "POST",
    body: JSON.stringify(body),
  })
}

export function savePreview(
  playlistId: string,
  revision: string,
  options: RequestInit = {},
): Promise<Job> {
  return request<Job>(`/job/${playlistId}/save`, {
    ...mutating(options),
    method: "POST",
    body: JSON.stringify({ revision }),
  })
}

export function restorePreview(
  playlistId: string,
  revision: string,
  options: RequestInit = {},
): Promise<Job> {
  return request<Job>(`/job/${playlistId}/restore`, {
    ...mutating(options),
    method: "POST",
    body: JSON.stringify({ revision }),
  })
}

export function getMatchCandidates(
  playlistId: string,
  occurrence: string,
  options: RequestInit = {},
): Promise<Candidate[]> {
  // Occurrences carry Spotify snapshot ids, which can contain slashes; encode the whole segment.
  return request<Candidate[]>(
    `/job/${playlistId}/matches/${encodeURIComponent(occurrence)}`,
    options,
  )
}

export function applyRecording(
  playlistId: string,
  occurrence: string,
  videoId: string,
  options: RequestInit = {},
): Promise<Job> {
  return request<Job>(`/job/${playlistId}/matches/${encodeURIComponent(occurrence)}`, {
    ...mutating(options),
    method: "POST",
    body: JSON.stringify({ video_id: videoId }),
  })
}

export async function logout(options: RequestInit = {}): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/auth/logout", { ...mutating(options), method: "POST" })
}
