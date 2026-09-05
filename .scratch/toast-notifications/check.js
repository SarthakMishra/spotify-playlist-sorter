// In a disposable browser tab, run installToastCheck as an init script before loading
// the Vite app at /playlists/toast-check, then run await checkToastNotifications().
// All /api requests are mocked, including Spotify saves.
function installToastCheck() {
  const tracks = ["First song", "Second song", "Third song"].map((name, index) => ({
    occurrence: `${index}:1`, id: String(index), name, artist: "Test artist",
    key: "8A", bpm: 120 + index, energy: 0.5,
  }))
  const state = window.toastCheck = {
    job: {
      playlist_id: "toast-check", revision: "1", name: "Weekend listening", status: "ready",
      completed: 3, total: 3, kept_count: 1, tracks, sorted_tracks: tracks,
      transitions: [], error: null,
    },
    rejectNext: false, failPoll: false, instant: false, requests: 0,
  }
  const originalFetch = window.fetch.bind(window)
  window.fetch = async (input, options = {}) => {
    const path = new URL(typeof input === "string" ? input : input.url, location.href).pathname
    if (!path.startsWith("/api/")) return originalFetch(input, options)
    const json = (body, status = 200) => Response.json(body, { status })
    if (path === "/api/session")
      return json({ configured: true, user: { id: "test", name: "Test" }, csrf: "mock" })
    if (path === "/api/playlists")
      return json([{ id: "toast-check", name: state.job.name, total: 4, image: null }])
    if (path === "/api/auth/logout") return json({ detail: "Please try again." }, 503)
    if (path === "/api/job")
      return state.failPoll ? json({ detail: "Connection interrupted." }, 503) : json(state.job)
    if (path === "/api/job/sort" || path === "/api/job/save") {
      state.requests++
      if (state.rejectNext) {
        state.rejectNext = false
        return json({ detail: "Temporarily unavailable. Please try again." }, 503)
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
  await wait(() => button("Sort again"), "Playlist did not load")
  assert(titles().length === 0, "An old result was replayed on mount")
  const before = [firstSongY(), previewY()]
  button("Sort again").click()
  await wait(() => shown("Finding a smooth order..."), "Sorting toast is missing")
  assert(button("Sort again").disabled && button("Save to Spotify").disabled, "Actions stay enabled while sorting")
  assert(firstSongY() === before[0] && previewY() === before[1], "Sorting shifted the page")
  state.job.status = "ready"
  await wait(() => shown("Your new order is ready"), "Sort completion is missing")
  assert(titles().length === 1, "Sort completion created duplicate toasts")
  button("Save to Spotify").click()
  await wait(() => shown("Saving to Spotify..."), "Saving toast is missing")
  assert(firstSongY() === before[0] && previewY() === before[1], "Saving shifted the page")
  state.job.status = "saved"
  await wait(() => shown("Saved to Spotify"), "Save completion is missing")
  assert(titles().length === 1, "Save completion created duplicate toasts")
  assert(!document.querySelector("main").textContent.includes("Saved to Spotify"), "Save success is still inline")
  await wait(() => titles().length === 0, "Success did not auto-dismiss", 6500)

  state.rejectNext = true
  button("Sort again").click()
  await wait(() => shown("Couldn't start the request"), "Request failure is missing")
  assert(!shown("Your new order is ready") && !shown("Saved to Spotify"), "Rejected request reported success")
  assert(!button("Sort again").disabled, "Rejected request cannot be retried")
  state.instant = true
  button("Sort again").click()
  await wait(() => shown("Your new order is ready"), "Immediate completion was missed")
  state.instant = false

  button("Sort again").click()
  await wait(() => shown("Finding a smooth order..."), "Retry did not show progress")
  state.failPoll = true
  await wait(() => button("Check progress"), "Polling recovery is missing")
  await wait(() => !shown("Finding a smooth order..."), "Polling failure left a stuck loading toast")
  state.failPoll = false
  button("Check progress").click()
  await wait(() => shown("Finding a smooth order..."), "Progress did not resume")
  state.job.status = "ready"
  await wait(() => shown("Your new order is ready"), "Recovered job did not complete")

  button("Save to Spotify").click()
  await wait(() => shown("Saving to Spotify..."), "Second save did not start")
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
