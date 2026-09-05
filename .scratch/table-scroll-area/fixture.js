// Browser navigation init script. Use in an isolated context with the local Vite server.
const tracks = Array.from({ length: 24 }, (_, index) => ({
  occurrence: String(index),
  id: String(index),
  name: `Song ${index + 1} with a longer title`,
  artist: "Example artist with a longer name",
  key: "8A",
  bpm: 100 + index,
  energy: 0.5,
}))
const fixtures = {
  "/api/session": { configured: true, user: { id: "test", name: "Test" }, csrf: "test" },
  "/api/playlists": [{ id: "test", name: "Scroll area preview", total: tracks.length, image: null }],
  "/api/job": {
    playlist_id: "test", revision: "test", name: "Scroll area preview", status: "ready",
    completed: tracks.length, total: tracks.length, kept_count: 0, error: null,
    tracks, sorted_tracks: tracks,
    transitions: tracks.slice(1).map((track, index) => ({
      index, track1_name: tracks[index].name, track2_name: track.name,
      key1: "8A", key2: "8A", bpm_diff: 1, energy_diff: 0, score: 0.9,
    })),
  },
}
const originalFetch = window.fetch
window.fetch = (input, options) => {
  const path = new URL(input instanceof Request ? input.url : input, location.href).pathname
  if (!path.startsWith("/api/")) return originalFetch(input, options)
  if (!fixtures[path] || (options?.method && options.method !== "GET")) {
    return Promise.reject(new Error(`Unexpected test request: ${path}`))
  }
  return Promise.resolve(Response.json(fixtures[path]))
}
localStorage.setItem("theme", "dark")
