// In a disposable browser tab, run installToastCheck as an init script before loading
// the Vite app at /playlists/toast-check, then run await checkToastNotifications().
// All /api requests are mocked, including Spotify saves.
function installToastCheck() {
  const tracks = ["First song", "Second song", "Third song"].map((name, index) => ({
    occurrence: `${index}:1`, id: String(index), name, artist: "Test artist",
    original_position: index, kind: "track", duration_ms: 180000,
    analysis_status: "ready", fixed_reason: null,
    key: "8A", bpm: 120 + index, energy: 0.5,
  }))
  const state = window.toastCheck = {
    job: {
      playlist_id: "toast-check", revision: "1", name: "Weekend listening", status: "ready",
      completed: 3, total: 3, kept_count: 0, tracks, sorted_tracks: tracks,
      analyzed_count: 3, cached_count: 0, recording_count: 3, metadata_loaded: true,
      profile: "smooth", first_occurrence: null, last_occurrence: null,
      can_restore: false, arrangement: null, review: null,
      transitions: [], error: null,
    },
    rejectNext: false, failPoll: false, instant: false, requests: 0,
    youtubeStatus: 200,
  }
  const analyzedJob = structuredClone(state.job)
  const originalFetch = window.fetch.bind(window)
  window.fetch = async (input, options = {}) => {
    const path = new URL(typeof input === "string" ? input : input.url, location.href).pathname
    if (!path.startsWith("/api/")) return originalFetch(input, options)
    const json = (body, status = 200) => Response.json(body, { status })
    if (path === "/api/session")
      return json({ configured: true, user: { id: "test", name: "Test" }, csrf: "mock" })
    if (path === "/api/playlists")
      return json([{ id: "toast-check", name: analyzedJob.name, total: 3, image: null }])
    if (path === "/api/auth/logout") return json({ detail: "Please try again." }, 503)
    if (path === "/api/youtube") {
      if (options.method === "POST" && state.youtubeStatus !== 200)
        return json({ detail: state.youtubeStatus === 422 ? "Choose a valid cookie export." : "Failed to fetch" }, state.youtubeStatus)
      return json({ mode: "anonymous", server_source: "anonymous", node_available: true, scripts_available: true, yt_dlp_version: "fixture" })
    }
    if (path === "/api/job") {
      if (state.failPoll) throw new TypeError("Failed to fetch")
      return json(state.job)
    }
    if (["/api/job/sort", "/api/job/save", "/api/playlists/toast-check/analyze"].includes(path)) {
      state.requests++
      if (state.rejectNext) {
        state.rejectNext = false
        return json({ detail: "Temporarily unavailable. Please try again." }, 503)
      }
      if (path.endsWith("analyze")) {
        state.job = { ...structuredClone(analyzedJob), status: "analyzing", sorted_tracks: [] }
        return json(state.job)
      }
      state.job.revision = String(state.requests + 1)
      state.job.error = null
      state.job.status = path.endsWith("sort")
        ? (state.instant ? "ready" : "sorting")
        : (state.instant ? "saved" : "saving")
      return json(state.job)
    }
    throw new Error(`Unexpected API request: ${path}`)
  }
}

async function checkToastNotifications() {
  const state = window.toastCheck
  if (!state) throw new Error("Install the API mocks before loading the page")
  const assert = (condition, message) => { if (!condition) throw new Error(message) }
  const wait = async (condition, message, timeout = 5000) => {
    const until = Date.now() + timeout
    while (!condition() && Date.now() < until)
      await new Promise((resolve) => setTimeout(resolve, 50))
    assert(condition(), message)
  }
  const button = (text) => [...document.querySelectorAll("button")]
    .find((item) => item.textContent.trim() === text)
  const titles = () => [...document.querySelectorAll('[data-slot="toast"]:not([data-ending-style]) [data-slot="toast-title"]')]
    .map((item) => item.textContent)
  const shown = (title) => titles().includes(title)
  const dismiss = () => document.querySelectorAll('[data-slot="toast-close"]')
    .forEach((item) => item.click())
  const firstSongY = () => document.getElementById("first-song").getBoundingClientRect().y
  const previewY = () => document.querySelector('[role="tablist"]').getBoundingClientRect().y
  await wait(() => button("Arrange again"), "Playlist did not load")
  assert(titles().length === 0, "An old result was replayed on mount")
  const before = [firstSongY(), previewY()]
  button("Arrange again").click()
  await wait(() => shown("Finding an order..."), "Sorting toast is missing")
  assert(button("Arrange again").disabled && button("Save to Spotify").disabled, "Actions stay enabled while sorting")
  assert(firstSongY() === before[0] && previewY() === before[1], "Sorting shifted the page")
  state.job.status = "ready"
  await wait(() => shown("Your new order is ready"), "Sort completion is missing")
  assert(titles().length === 1, "Sort completion created duplicate toasts")
  button("Save to Spotify").click()
  await wait(() => shown("Saving and verifying on Spotify..."), "Saving toast is missing")
  assert(firstSongY() === before[0] && previewY() === before[1], "Saving shifted the page")
  state.job.status = "saved"
  await wait(() => shown("Saved to Spotify"), "Save completion is missing")
  assert(titles().length === 1, "Save completion created duplicate toasts")
  assert(!document.querySelector('main [data-slot="alert"]'), "Save success added an inline banner")
  await wait(() => titles().length === 0, "Success did not auto-dismiss", 6500)

  state.rejectNext = true
  button("Arrange again").click()
  await wait(() => shown("Couldn't start the request"), "Request failure is missing")
  assert(!shown("Your new order is ready") && !shown("Saved to Spotify"), "Rejected request reported success")
  assert(!button("Arrange again").disabled, "Rejected request cannot be retried")
  state.instant = true
  button("Arrange again").click()
  await wait(() => shown("Your new order is ready"), "Immediate completion was missed")
  state.instant = false

  button("Arrange again").click()
  await wait(() => shown("Finding an order..."), "Retry did not show progress")
  state.failPoll = true
  await wait(() => button("Check progress"), "Polling recovery is missing")
  assert(shown("Couldn't check progress"), "Polling failure is an inline alert instead of a toast")
  assert(!document.querySelector("main").textContent.includes("Failed to fetch"), "Polling error is still inline")
  assert(document.querySelector('[data-slot="toast-action"]').textContent === "Check progress", "Toast retry is missing")
  await wait(() => !shown("Finding an order..."), "Polling failure left a stuck loading toast")
  state.failPoll = false
  document.querySelector('[data-slot="toast-action"]').click()
  await wait(() => shown("Finding an order..."), "Progress did not resume")
  assert(!shown("Couldn't check progress"), "Polling error survived retry")
  state.job.status = "ready"
  await wait(() => shown("Your new order is ready"), "Recovered job did not complete")

  button("Save to Spotify").click()
  await wait(() => shown("Saving and verifying on Spotify..."), "Second save did not start")
  state.job.status = "error"
  state.job.error = "Saving stopped. Some songs may have moved. Check the playlist again."
  await wait(() => shown("Couldn't finish the playlist"), "Failed save was reported as successful")
  dismiss()
  await wait(() => titles().length === 0, "Error did not dismiss")
  assert(document.querySelector("main").textContent.includes("Some songs may have moved"), "Interrupted-save warning disappeared with the toast")
  button("Sign out").click()
  await wait(() => shown("Couldn't sign out"), "Sign-out failure is missing")
  assert(!document.querySelector("main").textContent.includes("Couldn't sign out"), "Sign-out error is still inline")
  dismiss()
  assert(document.documentElement.scrollWidth <= document.documentElement.clientWidth, "Page overflows horizontally")
  return "Passed: sorting/saving without layout shifts, completion, dismissal, request failure, immediate completion, polling recovery, interrupted-save warning, sign-out error."
}
