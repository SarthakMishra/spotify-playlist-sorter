export type Session = {
  configured: boolean
  user: { id: string; name: string } | null
  csrf: string | null
}

export type Playlist = { id: string; name: string; total: number; image: string | null }
export type Track = {
  occurrence: string
  id: string
  name: string
  artist: string
  key: string
  bpm: number
  energy: number
}
export type Transition = {
  index: number
  track1_name: string
  track2_name: string
  key1: string
  key2: string
  bpm_diff: number | null
  energy_diff: number | null
  score: number | null
}
export type Job = {
  playlist_id: string
  revision: string
  name: string
  status: "analyzing" | "ready" | "sorting" | "saving" | "saved" | "error"
  completed: number
  total: number
  kept_count: number
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
  return !!job && ["analyzing", "sorting", "saving"].includes(job.status)
}
