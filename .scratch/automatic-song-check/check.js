// Run in an isolated browser page on the local Vite server. All API requests are mocked.
async function checkAutomaticSongCheck() {
  const assert = (condition, message) => {
    if (!condition) throw new Error(message)
  }
  const waitFor = async (condition) => {
    for (let i = 0; i < 200; i++) {
      if (condition()) return
      await new Promise(resolve => setTimeout(resolve, 20))
    }
    throw new Error("Timed out waiting for UI state")
  }
  const tracks = Array.from({ length: 4 }, (_, index) => ({
    id: String(index), occurrence: String(index), name: `Song ${index + 1}`,
    artist: "Example artist", key: "8A", bpm: 110, energy: 0.5,
  }))
  const ready = {
    playlist_id: "test", revision: "test", name: "Automatic check preview", status: "ready",
    total: 4, completed: 4, kept_count: 0, error: null, tracks, sorted_tracks: [], transitions: [],
  }
  let job = null
  let total = 4
  let starts = 0
  let aborts = 0
  let mode = "hold"
  let finishStart
  window.fetch = (input, options) => {
    const path = new URL(input instanceof Request ? input.url : input, location.href).pathname
    if (path === "/api/session") return Promise.resolve(Response.json({ configured: true, user: { id: "test", name: "Test" }, csrf: "test" }))
    if (path === "/api/playlists") return Promise.resolve(Response.json([{ id: "test", name: ready.name, total, image: null }]))
    if (path === "/api/job") return Promise.resolve(Response.json(job))
    if (path !== "/api/playlists/test/analyze") throw new Error(`Unexpected API request: ${path}`)
    assert(options.method === "POST" && options.headers.get("X-CSRF-Token") === "test", "Analysis request contract changed")
    starts++
    if (mode === "error") return Promise.resolve(Response.json({ detail: "Analysis temporarily unavailable" }, { status: 409 }))
    return new Promise((resolve, reject) => {
      finishStart = () => {
        job = { ...ready, status: "analyzing", total: 0, completed: 0, tracks: [] }
        resolve(Response.json(job, { status: 202 }))
      }
      options.signal.addEventListener("abort", () => {
        aborts++
        reject(new DOMException("Aborted", "AbortError"))
      }, { once: true })
      if (mode !== "hold") finishStart()
    })
  }
  const openPlaylist = async () => {
    document.querySelector('a[href="/playlists"]').click()
    await waitFor(() => location.pathname === "/playlists")
    const refresh = document.querySelector('button[aria-label="Refresh playlists"]')
    await waitFor(() => !refresh.disabled)
    refresh.click()
    await new Promise(resolve => setTimeout(resolve, 20))
    await waitFor(() => !refresh.disabled)
    document.querySelector('main a[href="/playlists/test"]').click()
    await waitFor(() => location.pathname === "/playlists/test")
  }
  const progress = () => document.querySelector('[role="progressbar"]')
  const text = () => document.querySelector("main").textContent
  const retry = () => [...document.querySelectorAll("button")].find(el => el.textContent.includes("Check again"))

  await openPlaylist()
  await waitFor(() => starts === 1)
  assert(progress() && text().includes("Getting ready"), "Opening a playlist did not show immediate progress")
  assert(!text().includes("Check songs") && !text().includes("Let's check"), "Redundant check step remains")
  const initialProgress = progress()
  finishStart()
  await waitFor(() => job?.status === "analyzing")
  assert(progress() === initialProgress, "Loading panel remounted when analysis started")
  job = { ...ready, status: "analyzing", completed: 2, tracks: [] }
  await waitFor(() => progress()?.getAttribute("aria-valuenow") === "2")
  assert(text().includes("2 of 4"), "Progress count is wrong")
  job = ready
  await waitFor(() => text().includes("First song") && !progress())
  assert(starts === 1, "Strict Mode or polling started analysis more than once")
  await openPlaylist()
  assert(text().includes("First song") && starts === 1, "Existing ready job was restarted")

  mode = "error"
  job = null
  await openPlaylist()
  await waitFor(() => retry())
  assert(starts === 2 && text().includes("Analysis temporarily unavailable") && !progress(), "Failed startup has no recovery state")
  await new Promise(resolve => setTimeout(resolve, 100))
  assert(starts === 2, "Failed startup retried automatically")
  mode = "success"
  retry().click()
  await waitFor(() => starts === 3 && progress())

  job = { ...ready, playlist_id: "other", status: "analyzing" }
  await openPlaylist()
  assert(text().includes("Another playlist") && !progress() && starts === 3, "Started over another active job")
  job = null
  total = 0
  await openPlaylist()
  assert(text().includes("This playlist is empty") && !progress() && starts === 3, "Empty playlist started analysis")

  total = 4
  mode = "hold"
  await openPlaylist()
  await waitFor(() => starts === 4)
  document.querySelector('a[href="/playlists"]').click()
  await waitFor(() => location.pathname === "/playlists")
  assert(aborts >= 1, "Leaving the page did not abort the pending request")
  job = { ...ready, status: "analyzing", completed: 2, tracks: [] }
  await openPlaylist()
  assert(progress() && starts === 4, "Existing analysis was restarted")
  return { starts, aborts, immediateLoading: true, progress: true, retry: true, existingJob: true, busyJob: true, emptyPlaylist: true }
}
