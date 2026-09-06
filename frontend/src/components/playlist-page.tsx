import { lazy, Suspense, useEffect, useEffectEvent, useRef, useState } from "react"
import { Link, useLoaderData, useParams, useRouteLoaderData } from "react-router"
import { ArrowLeft, ArrowRight, ExternalLink, LoaderCircle, Music2 } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button, buttonVariants } from "@/components/ui/button"
import {
  Combobox,
  ComboboxInput,
  ComboboxContent,
  ComboboxList,
  ComboboxItem,
  ComboboxEmpty,
} from "@/components/ui/combobox"
import { Progress, ProgressLabel, ProgressValue } from "@/components/ui/progress"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { toast } from "@/components/ui/toast"
import {
  Table,
  TableHeader,
  TableHead,
  TableRow,
  TableBody,
  TableCell,
  TableCaption,
} from "@/components/ui/table"
import {
  api,
  ApiError,
  isWorking,
  type Job,
  type Playlist,
  type Profile,
  type Session,
  type Track,
} from "@/lib/api"

const SongDetails = lazy(() => import("@/components/song-details"))

export function PlaylistRoute() {
  const { playlistId } = useParams()
  const playlists = useRouteLoaderData<Playlist[]>("playlists") ?? []
  const initialJob = useLoaderData<Job | null>()
  const playlist = playlists.find((item) => item.id === playlistId)
  if (!playlist)
    return (
      <section>
        <h1 className="text-2xl font-semibold">Playlist not found</h1>
        <Link to="/playlists" className="mt-4 inline-block underline">
          Choose another playlist
        </Link>
      </section>
    )
  return <PlaylistPage key={playlistId} playlist={playlist} initialJob={initialJob} />
}

function SongList({
  tracks,
  label,
  checking = false,
}: {
  tracks: Track[]
  label: string
  checking?: boolean
}) {
  const states = {
    pending: "Waiting to check",
    matching: "Finding recording",
    downloading: "Downloading audio",
    analyzing: "Measuring audio",
    ready: "Checked",
    uncertain: "Recording uncertain",
    error: "Check failed",
    fixed: "Kept in place",
  }
  return (
    <Table className="table-fixed" scrollLabel={label}>
      <TableCaption className="sr-only">{label}</TableCaption>
      <TableHeader>
        <TableRow>
          <TableHead className="w-12">#</TableHead>
          <TableHead>Song</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {tracks.map((track, index) => (
          <TableRow key={track.occurrence}>
            <TableCell className="py-2.5 align-top text-muted-foreground tabular-nums">
              {index + 1}
            </TableCell>
            <TableCell className="py-2.5 whitespace-normal">
              <p className="wrap-break-words font-medium">{track.name}</p>
              <p className="wrap-break-words mt-0.5 text-muted-foreground">{track.artist}</p>
              {checking && !track.fixed_reason && (
                <p className="mt-1 text-xs text-muted-foreground">
                  {states[track.analysis_status]}
                </p>
              )}
              {track.fixed_reason && (
                <p className="mt-1 text-xs text-muted-foreground">
                  Kept in place · {track.fixed_reason}
                </p>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function ReviewSummary({ job }: { job: Job }) {
  const review = job.review
  if (!review) return null
  return (
    <section aria-label="Review summary" className="mt-4 space-y-3">
      {review.original_assessed !== null && review.suggested_assessed !== null ? (
        <>
          <dl className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <dt className="text-muted-foreground">Original transitions</dt>
              <dd className="mt-1 font-medium">
                {review.original_assessed} of {review.total_edges} assessed
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Suggested transitions</dt>
              <dd className="mt-1 font-medium">
                {review.suggested_assessed} of {review.total_edges} assessed
              </dd>
            </div>
          </dl>
          <p className="text-xs leading-5 text-muted-foreground">
            These counts show where boundary measurements are available.
          </p>
        </>
      ) : (
        <p className="text-sm text-muted-foreground">
          Transition estimates are unavailable for this arrangement.
        </p>
      )}
      {review.highlights.length > 0 ? (
        <details className="rounded-xl border p-4">
          <summary className="cursor-pointer rounded-sm text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring">
            {review.highlights.length}{" "}
            {review.highlights.length === 1 ? "transition" : "transitions"} worth checking
          </summary>
          <p className="mt-3 text-xs leading-5 text-muted-foreground">
            These notes describe measured changes and nearby artist repeats. Use your listening
            preference to judge them.
          </p>
          <ol className="mt-3 divide-y">
            {review.highlights.map((note) => (
              <li key={note.track1_occurrence} className="py-3 text-sm first:pt-0 last:pb-0">
                <p className="wrap-break-words font-medium">
                  {note.index}. {note.track1_name} → {note.index + 1}. {note.track2_name}
                </p>
                <p className="mt-1 leading-6 text-muted-foreground">{note.text}</p>
              </li>
            ))}
          </ol>
        </details>
      ) : (
        review.suggested_assessed !== null && (
          <p className="text-sm text-muted-foreground">
            {review.suggested_assessed === 0
              ? "There is not enough boundary evidence for listening notes."
              : "No standout changes were found in the assessed boundaries."}
          </p>
        )
      )}
    </section>
  )
}

function SongPicker({
  id,
  label,
  tracks,
  value,
  onChange,
  disabled,
}: {
  id: string
  label: string
  tracks: Track[]
  value: string | null
  onChange: (value: string | null) => void
  disabled: boolean
}) {
  const selected = tracks.find((track) => track.occurrence === value) ?? null
  return (
    <div className="min-w-0 space-y-2">
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      <Combobox
        items={tracks}
        value={selected}
        disabled={disabled}
        onValueChange={(track) => onChange(track?.occurrence ?? null)}
        itemToStringLabel={(track) =>
          `${track.name} · ${track.artist} · Originally #${track.original_position + 1}`
        }
        itemToStringValue={(track) => track.occurrence}
        isItemEqualToValue={(a, b) => a.occurrence === b.occurrence}
      >
        <ComboboxInput
          id={id}
          className="w-full"
          placeholder="Choose for me"
          showClear={!!selected && !disabled}
          disabled={disabled}
        />
        <ComboboxContent>
          <ComboboxEmpty>No songs found.</ComboboxEmpty>
          <ComboboxList>
            {(track: Track) => (
              <ComboboxItem key={track.occurrence} value={track}>
                <div className="min-w-0">
                  <p className="truncate">{track.name}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {track.artist} · Originally #{track.original_position + 1}
                  </p>
                </div>
              </ComboboxItem>
            )}
          </ComboboxList>
        </ComboboxContent>
      </Combobox>
      {selected && (
        <p className="text-xs text-muted-foreground">
          Originally #{selected.original_position + 1}
        </p>
      )}
    </div>
  )
}

function PlaylistPage({ playlist, initialJob }: { playlist: Playlist; initialJob: Job | null }) {
  const session = useRouteLoaderData<Session>("root")
  const [job, setJob] = useState(initialJob?.playlist_id === playlist.id ? initialJob : null)
  const [error, setError] = useState("")
  const [pending, setPending] = useState<"analyze" | "sort" | "save" | "restore" | null>(null)
  const [profile, setProfile] = useState<Profile>(initialJob?.profile ?? "smooth")
  const [firstOccurrence, setFirstOccurrence] = useState<string | null>(
    initialJob?.first_occurrence ?? null,
  )
  const [lastOccurrence, setLastOccurrence] = useState<string | null>(
    initialJob?.last_occurrence ?? null,
  )
  const actionController = useRef<AbortController | null>(null)
  const progressToast = useRef<string | null>(null)
  const reviewHeading = useRef<HTMLHeadingElement>(null)
  const errorRegion = useRef<HTMLDivElement>(null)
  const actionFocus = useRef<{ element: Element | null; failed: boolean } | null>(null)
  const jobStatus = job?.status
  const busy = pending !== null || isWorking(job)
  const activity =
    pending === "sort"
      ? "sorting"
      : pending === "save"
        ? "saving"
        : pending === "restore"
          ? "restoring"
          : jobStatus
  const otherJob =
    initialJob?.playlist_id !== playlist.id && isWorking(initialJob) ? initialJob : null
  const checking =
    pending === "analyze" ||
    jobStatus === "analyzing" ||
    (!job && !otherJob && playlist.total > 0 && !error)
  const tracks = job?.tracks ?? []
  const choices = tracks.filter(
    (track) => track.analysis_status === "ready" && track.fixed_reason === null,
  )
  const canSort = choices.length >= 2
  const opening = tracks[0]
  const closing = tracks.at(-1)
  const fixedFirst = opening?.fixed_reason ? opening : null
  const fixedLast = closing?.fixed_reason ? closing : null
  const pinConflict = firstOccurrence !== null && firstOccurrence === lastOccurrence
  const hasPreview = !!job?.sorted_tracks.length && job.status !== "error"
  const choicesChanged =
    hasPreview &&
    (profile !== job?.profile ||
      firstOccurrence !== job.first_occurrence ||
      lastOccurrence !== job.last_occurrence)

  const statusMessage = checking
    ? job?.metadata_loaded
      ? `${job.completed} of ${job.total} checks finished. ${job.analyzed_count} checked successfully.`
      : "Loading playlist."
    : activity === "sorting"
      ? "Arranging the playlist."
      : activity === "saving"
        ? "Saving to Spotify."
        : activity === "restoring"
          ? "Restoring the previous order on Spotify."
          : jobStatus === "restored"
            ? "Previous order restored on Spotify."
            : choicesChanged
              ? "Arrange again to apply your choices."
              : jobStatus === "saved"
                ? "Saved to Spotify."
                : hasPreview
                  ? job?.arrangement?.unchanged
                    ? "Your order is unchanged."
                    : "Suggested order ready."
                  : jobStatus === "ready"
                    ? `${job?.analyzed_count ?? 0} checked successfully. ${job?.kept_count ?? 0} kept in place.`
                    : ""

  useEffect(() => {
    const requested = actionFocus.current
    if (busy || !requested) return
    actionFocus.current = null
    if (document.activeElement !== requested.element && document.activeElement !== document.body)
      return
    if (requested.failed) {
      if (requested.element instanceof HTMLElement && requested.element.isConnected)
        requested.element.focus()
    } else if (jobStatus === "error") errorRegion.current?.focus()
    else if (hasPreview) reviewHeading.current?.focus()
  }, [busy, hasPreview, jobStatus])

  const startChecking = useEffectEvent(() => {
    if (!job && !otherJob && playlist.total > 0) void run("analyze")
  })

  useEffect(() => {
    // Let Strict Mode's setup/cleanup pass finish before starting a server job.
    const timer = setTimeout(() => startChecking(), 0)
    return () => clearTimeout(timer)
  }, [playlist.id])

  useEffect(
    () => () => {
      actionController.current?.abort()
      if (progressToast.current) toast.close(progressToast.current)
      progressToast.current = null
    },
    [],
  )

  useEffect(() => {
    if (!error) return undefined
    return () => toast.close(`playlist-error-${playlist.id}`)
  }, [error, playlist.id])

  useEffect(() => {
    if (error) {
      if (progressToast.current) toast.close(progressToast.current)
      progressToast.current = null
    } else if (activity === "sorting" || activity === "saving" || activity === "restoring") {
      progressToast.current = toast.add({
        id: `playlist-${playlist.id}`,
        title:
          activity === "sorting"
            ? "Finding an order..."
            : activity === "restoring"
              ? "Restoring previous order..."
              : "Saving and verifying on Spotify...",
        description: playlist.name,
        type: "loading",
        priority: "low",
        timeout: 0,
      })
    } else if (progressToast.current) {
      const failed = activity === "error"
      toast.add({
        id: progressToast.current,
        title: failed
          ? "Couldn't finish the playlist"
          : activity === "saved"
            ? "Saved to Spotify"
            : activity === "restored"
              ? "Previous order restored on Spotify"
              : job?.arrangement?.unchanged
                ? "Your order is unchanged"
                : "Your new order is ready",
        description: job?.error || playlist.name,
        type: failed ? "error" : "success",
        priority: failed ? "high" : "low",
        timeout: failed ? 8000 : 5000,
      })
      progressToast.current = null
    }
  }, [activity, error, job?.error, job?.arrangement?.unchanged, playlist.id, playlist.name])

  useEffect(() => {
    if (error || !jobStatus || !["analyzing", "sorting", "saving", "restoring"].includes(jobStatus))
      return undefined
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    async function poll() {
      try {
        const next = await api<Job | null>("/job", { signal: controller.signal })
        if (controller.signal.aborted) return
        if (!next || next.playlist_id !== playlist.id)
          throw new Error("This playlist changed in another tab. Reload the page to continue.")
        setJob(next)
        if (isWorking(next)) timer = setTimeout(poll, 1000)
      } catch (err) {
        if (controller.signal.aborted) return
        if (err instanceof ApiError && err.status === 401) {
          window.location.assign("/")
          return
        }
        const message =
          err instanceof Error ? err.message : "We couldn't check progress. Please try again."
        setError(message)
        toast.add({
          id: `playlist-error-${playlist.id}`,
          title: "Couldn't check progress",
          description: message,
          type: "error",
          priority: "high",
          timeout: 0,
          actionProps: { children: "Check progress", onClick: () => setError("") },
        })
      }
    }
    timer = setTimeout(poll, 700)
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
    // Status controls the polling lifetime. Each request schedules the next one after it finishes.
  }, [jobStatus, playlist.id, error])

  async function run(action: "analyze" | "sort" | "save" | "restore") {
    if (busy) return
    const controller = new AbortController()
    actionController.current = controller
    if (action !== "analyze")
      actionFocus.current = { element: document.activeElement, failed: false }
    setPending(action)
    setError("")
    const path = action === "analyze" ? `/playlists/${playlist.id}/analyze` : `/job/${action}`
    try {
      const next = await api<Job>(path, {
        method: "POST",
        signal: controller.signal,
        headers: { "X-CSRF-Token": session?.csrf ?? "" },
        body:
          action === "analyze"
            ? null
            : JSON.stringify({
                revision: job?.revision,
                ...(action === "sort"
                  ? { profile, first_occurrence: firstOccurrence, last_occurrence: lastOccurrence }
                  : {}),
              }),
      })
      if (controller.signal.aborted) return
      if (action === "analyze" || action === "restore") {
        setFirstOccurrence(null)
        setLastOccurrence(null)
      }
      setJob(next)
    } catch (err) {
      if (controller.signal.aborted) return
      if (err instanceof ApiError && err.status === 401) {
        window.location.assign("/")
        return
      }
      if (actionFocus.current) actionFocus.current.failed = true
      const message = err instanceof Error ? err.message : "Please try again."
      if (action === "analyze") setError(message)
      toast.add({
        id:
          action === "analyze"
            ? `playlist-error-${playlist.id}`
            : (progressToast.current ?? undefined),
        title: action === "analyze" ? "Couldn't check songs" : "Couldn't start the request",
        description: message,
        type: "error",
        priority: "high",
        timeout: action === "analyze" ? 0 : 8000,
        actionProps:
          action === "analyze"
            ? { children: "Check again", onClick: () => void run("analyze") }
            : undefined,
      })
      progressToast.current = null
    } finally {
      if (!controller.signal.aborted) setPending(null)
    }
  }

  return (
    <section className="mx-auto max-w-2xl">
      <output className="sr-only">{statusMessage}</output>
      <Link
        to="/playlists"
        className="mb-5 inline-flex min-h-8 items-center gap-2 rounded-md text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        Your playlists
      </Link>
      <div className="flex items-center gap-4">
        {playlist.image ? (
          <img
            src={playlist.image}
            alt=""
            width={64}
            height={64}
            className="size-16 shrink-0 rounded-xl object-cover"
          />
        ) : (
          <div className="flex size-16 shrink-0 items-center justify-center rounded-xl bg-muted">
            <Music2 className="size-7 text-muted-foreground" aria-hidden="true" />
          </div>
        )}
        <div className="min-w-0">
          <h1 className="wrap-break-words text-2xl font-semibold tracking-tight sm:text-3xl">
            {playlist.name}
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {job?.metadata_loaded ? tracks.length : playlist.total} items
          </p>
        </div>
      </div>

      {pending !== "analyze" && job?.error && (
        <div
          ref={errorRegion}
          tabIndex={-1}
          className="mt-7 rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Alert variant="destructive">
            <AlertDescription>{job.error}</AlertDescription>
          </Alert>
        </div>
      )}

      {error && isWorking(job) && (
        <Button className="mt-5" size="sm" variant="outline" onClick={() => setError("")}>
          Check progress
        </Button>
      )}

      {otherJob && !job && (
        <Alert className="mt-8">
          <AlertDescription>
            Another playlist is still being checked.
            <Link to={`/playlists/${otherJob.playlist_id}`} className="underline">
              See progress
            </Link>
          </AlertDescription>
        </Alert>
      )}

      {((!job && !otherJob && playlist.total === 0) ||
        (jobStatus === "ready" && !tracks.length)) && (
        <p className="mt-8 text-sm text-muted-foreground">
          This playlist is empty. Add some songs on Spotify first.
        </p>
      )}

      {!checking && !otherJob && (jobStatus === "error" || (!job && error)) && (
        <Button
          className="mt-5"
          onClick={() => void run("analyze")}
          disabled={busy || playlist.total === 0}
        >
          Check again
          <ArrowRight aria-hidden="true" />
        </Button>
      )}

      {checking && (
        <div className="my-8 rounded-xl border bg-muted/20 p-5 sm:p-6">
          <Progress
            className="items-center gap-y-4"
            value={jobStatus === "analyzing" && job?.total ? job.completed : null}
            max={job?.total || 100}
          >
            <h2>
              <ProgressLabel className="flex items-center gap-2 text-base font-semibold">
                <LoaderCircle className="size-4 motion-safe:animate-spin" aria-hidden="true" />
                {job?.metadata_loaded ? "Checking songs" : "Loading playlist"}
              </ProgressLabel>
            </h2>
            <ProgressValue className="text-xs">
              {() =>
                jobStatus === "analyzing" && job?.total
                  ? `${job.completed} of ${job.total} checks finished`
                  : "Getting the song list"
              }
            </ProgressValue>
          </Progress>
          {job?.metadata_loaded && (
            <p className="mt-3 text-sm text-muted-foreground">
              {job.analyzed_count} songs checked successfully. {job.kept_count} items kept in place
              so far.
            </p>
          )}
          <p className="mt-4 text-sm leading-6 text-muted-foreground">
            You can leave this page and come back. Your playlist stays as it is until you save.
          </p>
        </div>
      )}

      {!!tracks.length && job && (
        <>
          {!checking && job.status !== "error" && (
            <div className="mt-6 border-t pt-5">
              {canSort ? (
                <div className="space-y-5">
                  <fieldset disabled={busy}>
                    <legend className="text-base font-semibold">Listening style</legend>
                    <div className="mt-3 flex flex-col gap-3 sm:flex-row">
                      {(["smooth", "variety"] as const).map((value) => (
                        <label
                          key={value}
                          htmlFor={`profile-${value}`}
                          aria-label={value === "smooth" ? "Smooth" : "More variety"}
                          className="flex flex-1 cursor-pointer items-start gap-3 rounded-xl border p-3 text-sm has-checked:border-foreground/40 has-checked:bg-muted/40"
                        >
                          <input
                            id={`profile-${value}`}
                            type="radio"
                            name="listening-profile"
                            value={value}
                            checked={profile === value}
                            onChange={() => setProfile(value)}
                            className="mt-1 accent-foreground"
                          />
                          <span>
                            <span className="block font-medium">
                              {value === "smooth" ? "Smooth" : "More variety"}
                            </span>
                            <span className="mt-1 block text-muted-foreground">
                              {value === "smooth"
                                ? "Gentler changes between songs."
                                : "More space between repeated artists and similar sounds."}
                            </span>
                          </span>
                        </label>
                      ))}
                    </div>
                  </fieldset>
                  <div>
                    <p className="mb-3 text-sm text-muted-foreground">
                      Choose a first or last song, or leave them for us to arrange.
                    </p>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div>
                        <SongPicker
                          id="first-song"
                          label="First song"
                          tracks={fixedFirst ? [fixedFirst] : choices}
                          value={fixedFirst?.occurrence ?? firstOccurrence}
                          onChange={setFirstOccurrence}
                          disabled={busy || !!fixedFirst}
                        />
                        {fixedFirst && (
                          <p className="mt-2 text-xs text-muted-foreground">
                            This item stays first. {fixedFirst.fixed_reason}.
                          </p>
                        )}
                      </div>
                      <div>
                        <SongPicker
                          id="last-song"
                          label="Last song"
                          tracks={fixedLast ? [fixedLast] : choices}
                          value={fixedLast?.occurrence ?? lastOccurrence}
                          onChange={setLastOccurrence}
                          disabled={busy || !!fixedLast}
                        />
                        {fixedLast && (
                          <p className="mt-2 text-xs text-muted-foreground">
                            This item stays last. {fixedLast.fixed_reason}.
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                  {job.kept_count > 0 && (
                    <div className="flex flex-wrap items-center gap-3 text-sm">
                      <Button variant="outline" disabled={busy} onClick={() => void run("analyze")}>
                        Check songs again
                      </Button>
                      <Link to="/youtube" className="underline underline-offset-4">
                        YouTube access
                      </Link>
                    </div>
                  )}
                  {pinConflict && (
                    <p role="alert" className="text-sm text-destructive">
                      Choose different entries for the first and last songs.
                    </p>
                  )}
                  <Button
                    variant={hasPreview ? "outline" : "default"}
                    onClick={() => void run("sort")}
                    disabled={busy || pinConflict}
                  >
                    {hasPreview ? "Arrange again" : "Arrange playlist"}
                    <ArrowRight aria-hidden="true" />
                  </Button>
                </div>
              ) : (
                <div className="space-y-3">
                  <p className="text-sm text-muted-foreground">
                    {choices.length === 0
                      ? "None of these songs could be checked. Your playlist stays in its original order."
                      : "Only one song can move. At least two checked songs are needed to rearrange this playlist."}
                  </p>
                  <Button variant="outline" onClick={() => void run("analyze")} disabled={busy}>
                    Check again
                  </Button>
                </div>
              )}
            </div>
          )}
          {!checking && job.status !== "error" && (
            <p id="review-coverage" className="mt-5 text-sm text-muted-foreground">
              {job.analyzed_count} {job.analyzed_count === 1 ? "song checked" : "songs checked"}.{" "}
              {job.kept_count} {job.kept_count === 1 ? "item stays" : "items stay"} in place.
              {job.cached_count > 0 &&
                ` ${job.cached_count} checked ${job.cached_count === 1 ? "song reused" : "songs reused"} earlier analysis.`}
            </p>
          )}
          {job.status === "error" && (
            <p className="mt-5 text-sm text-muted-foreground">
              This is the order last loaded. Check again to see the current Spotify playlist.
            </p>
          )}
          {hasPreview && (
            <div className="mt-6 flex flex-col gap-3 border-t pt-5 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2
                  ref={reviewHeading}
                  tabIndex={-1}
                  aria-describedby="review-coverage"
                  className="rounded-sm text-base font-semibold outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {job.status === "restored" ? "Restored order" : "Playlist preview"}
                </h2>
                <p aria-live="polite" className="mt-1 text-sm text-muted-foreground">
                  {job.status === "restored"
                    ? "Previous order restored and verified on Spotify."
                    : job.status === "saved"
                      ? "Saved and verified on Spotify."
                      : choicesChanged
                        ? "Arrange again to apply your choices."
                        : job.arrangement?.unchanged
                          ? "This is already your saved order."
                          : "Review the song order below."}
                </p>
              </div>
              {job.status === "saved" || job.status === "restored" || job.arrangement?.unchanged ? (
                <a
                  className={buttonVariants({ variant: "outline" })}
                  aria-label="Open Spotify"
                  href={`https://open.spotify.com/playlist/${playlist.id}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open Spotify
                  <ExternalLink aria-hidden="true" />
                </a>
              ) : (
                <Button
                  onClick={() => void run("save")}
                  disabled={busy || choicesChanged || pinConflict}
                >
                  Save to Spotify
                </Button>
              )}
            </div>
          )}
          {job.can_restore && job.status !== "error" && (
            <div className="mt-4 space-y-2">
              <Button
                variant="outline"
                onClick={() => void run("restore")}
                disabled={busy}
                aria-describedby="restore-limit"
              >
                Restore previous order
              </Button>
              <p id="restore-limit" className="text-xs leading-5 text-muted-foreground">
                Undoes your most recent save in this session, if Spotify is still unchanged.
                Checking a playlist again, signing out, session expiry or a server restart removes
                this option.
              </p>
            </div>
          )}
          {hasPreview && !choicesChanged && <ReviewSummary job={job} />}
          {hasPreview && !choicesChanged && job.arrangement?.same_as_other_profile && (
            <p className="mt-3 text-sm text-muted-foreground">
              Both styles found the same order with these song choices.
            </p>
          )}
          {hasPreview && !choicesChanged && job.arrangement?.limited && (
            <p className="mt-3 text-sm text-muted-foreground">
              This playlist is too large for a full search. Your first and last song choices were
              applied; the other songs keep their original relative order.
            </p>
          )}
          <div className="mt-5">
            {hasPreview ? (
              <Tabs
                className="gap-4"
                defaultValue="new"
                key={job.sorted_tracks.map((track) => track.occurrence).join(",")}
              >
                <TabsList
                  aria-label="Playlist preview"
                  className="w-full bg-muted/70 sm:w-fit dark:bg-muted/50"
                >
                  <TabsTrigger value="new">
                    {job.status === "restored" ? "Restored" : "Suggested"}
                  </TabsTrigger>
                  <TabsTrigger value="original">Original</TabsTrigger>
                  {job.status !== "restored" && <TabsTrigger value="details">Compare</TabsTrigger>}
                </TabsList>
                <TabsContent value="new">
                  <SongList
                    tracks={job.sorted_tracks}
                    label={
                      job.status === "restored" ? "Restored song order" : "Suggested song order"
                    }
                  />
                </TabsContent>
                <TabsContent value="original">
                  <SongList tracks={tracks} label="Original song order" />
                </TabsContent>
                <TabsContent value="details">
                  <Suspense
                    fallback={
                      <output className="block py-5 text-sm text-muted-foreground">
                        Loading details...
                      </output>
                    }
                  >
                    <SongDetails
                      original={tracks}
                      tracks={job.sorted_tracks}
                      transitions={job.transitions}
                    />
                  </Suspense>
                </TabsContent>
              </Tabs>
            ) : (
              <SongList
                tracks={tracks}
                label={job.status === "error" ? "Order last loaded" : "Songs in your playlist"}
                checking={checking}
              />
            )}
          </div>
        </>
      )}
    </section>
  )
}
