import { useEffect, useEffectEvent, useRef, useState } from "react"
import { Link, useLoaderData, useParams, useRouteLoaderData } from "react-router"
import { ArrowLeft, ArrowRight, ExternalLink, LoaderCircle, Music2 } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Progress, ProgressLabel, ProgressValue } from "@/components/ui/progress"
import { toast } from "@/components/ui/toast"
import { CheckStep } from "@/components/steps/check-step"
import { PreferencesStep } from "@/components/steps/preferences-step"
import { ReviewStep } from "@/components/steps/review-step"
import {
  api,
  ApiError,
  isRematchStage,
  isWorking,
  type Job,
  type Options,
  type Playlist,
  type Session,
  type Track,
} from "@/lib/api"
import { DEFAULT_PREFERENCES, matchAttention } from "@/lib/preferences"

type StepId = "check" | "preferences" | "review"

function initialStep(job: Job | null): StepId {
  if (job?.sorted_tracks?.length) return "review"
  if (job && job.metadata_loaded) {
    const noted = job.tracks.some((track) => matchAttention(track) !== null)
    if (!noted) return "preferences"
  }
  return "check"
}

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

function PlaylistPage({ playlist, initialJob }: { playlist: Playlist; initialJob: Job | null }) {
  const session = useRouteLoaderData<Session>("root")
  // The session holds a single job slot, whichever playlist it owns. Polling keeps it
  // fresh so blocked states clear as soon as the working job finishes.
  const [sessionJob, setSessionJob] = useState<Job | null>(initialJob)
  const job = sessionJob?.playlist_id === playlist.id ? sessionJob : null
  const [step, setStep] = useState<StepId>(() => initialStep(initialJob))
  const [error, setError] = useState("")
  const [pending, setPending] = useState<"analyze" | "sort" | "save" | "restore" | null>(null)
  const [preferences, setPreferences] = useState<Options>(
    initialJob?.options
      ? {
          preset: initialJob.options.preset,
          pace: initialJob.options.pace,
          energy: initialJob.options.energy,
          variety: initialJob.options.variety,
        }
      : DEFAULT_PREFERENCES,
  )
  const [firstOccurrence, setFirstOccurrence] = useState<string | null>(
    job?.first_occurrence ?? null,
  )
  const [lastOccurrence, setLastOccurrence] = useState<string | null>(job?.last_occurrence ?? null)
  const [placements, setPlacements] = useState<Record<string, number>>(job?.placements ?? {})
  const actionController = useRef<AbortController | null>(null)
  const progressToast = useRef<string | null>(null)
  const reviewHeading = useRef<HTMLHeadingElement>(null)
  const errorRegion = useRef<HTMLDivElement>(null)
  const actionFocus = useRef<{ element: Element | null; failed: boolean } | null>(null)
  const advanceToReview = useRef(false)
  const rematch = useRef<{ occurrence: string } | null>(null)
  const jobStatus = job?.status
  const sessionJobStatus = sessionJob?.status
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
    sessionJob && sessionJob.playlist_id !== playlist.id && isWorking(sessionJob)
      ? sessionJob
      : null
  const analyzing = pending === "analyze" || jobStatus === "analyzing"
  const tracks = job?.tracks ?? []
  const choices = tracks.filter(
    (track) => track.analysis_status === "ready" && track.fixed_reason === null,
  )
  const canSort = choices.length >= 2
  const total = tracks.length
  const fixedTracks = tracks.filter((track) => track.fixed_reason)
  const fixedFirst =
    fixedTracks.find((track) => (placements[track.occurrence] ?? track.original_position) === 0) ??
    null
  const fixedLast =
    fixedTracks.find(
      (track) => (placements[track.occurrence] ?? track.original_position) === total - 1,
    ) ?? null
  const pinConflict = firstOccurrence !== null && firstOccurrence === lastOccurrence
  const placementConflict = fixedTracks.some((track, index) =>
    fixedTracks.some(
      (other, otherIndex) =>
        otherIndex !== index &&
        (placements[other.occurrence] ?? other.original_position) ===
          (placements[track.occurrence] ?? track.original_position),
    ),
  )
    ? "Two unanalyzable items claim the same position. Choose different positions."
    : null
  const hasPreview = !!job?.sorted_tracks.length && job.status !== "error"
  const placementsChanged =
    hasPreview &&
    fixedTracks.some(
      (track) =>
        (placements[track.occurrence] ?? track.original_position) !==
        (job.placements[track.occurrence] ?? track.original_position),
    )
  const choicesChanged =
    hasPreview &&
    !!job &&
    (preferences.preset !== job.options.preset ||
      preferences.pace !== job.options.pace ||
      preferences.energy !== job.options.energy ||
      preferences.variety !== job.options.variety ||
      firstOccurrence !== job.first_occurrence ||
      lastOccurrence !== job.last_occurrence ||
      placementsChanged)
  const movedCount =
    hasPreview && job
      ? job.sorted_tracks.filter((track, index) => track.original_position !== index).length
      : 0

  const statusMessage = analyzing
    ? job?.metadata_loaded
      ? `${job.completed} of ${job.total} analyzed. ${job.analyzed_count} analyzed successfully.`
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
                    ? `${job?.analyzed_count ?? 0} analyzed successfully. ${job?.kept_count ?? 0} can't be analyzed.`
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
  }, [busy, jobStatus])

  useEffect(() => {
    if (advanceToReview.current && jobStatus === "ready" && hasPreview) {
      advanceToReview.current = false
      setStep("review")
    }
  }, [jobStatus, hasPreview])

  // A clean analysis needs no check step; land straight on preferences instead.
  const skipCleanCheckStep = useEffectEvent((next: Job) => {
    if (
      next.status === "ready" &&
      next.playlist_id === playlist.id &&
      next.tracks.every((track) => matchAttention(track) === null)
    )
      setStep((current) => (current === "check" ? "preferences" : current))
  })

  // Resolve the pending rematch toast once polling sees the song leave the working stages.
  const observeRematch = useEffectEvent((next: Job) => {
    const active = rematch.current
    if (!active || next.playlist_id !== playlist.id) return
    const track = next.tracks.find((item) => item.occurrence === active.occurrence)
    if (!track || isRematchStage(track.analysis_status)) return
    rematch.current = null
    toast.close(`rematch-${active.occurrence}`)
    if (track.analysis_status === "ready" && next.status === "ready") {
      toast.add({
        title: "Recording updated",
        description: track.name,
        type: "success",
        priority: "low",
        timeout: 5000,
      })
    } else {
      toast.add({
        title: "Couldn't update the recording",
        description: next.error ?? track.fixed_reason ?? "Please try again.",
        type: "error",
        priority: "high",
        timeout: 8000,
      })
    }
  })

  const focusReviewHeading = useEffectEvent((active: boolean) => {
    if (active) reviewHeading.current?.focus()
  })

  useEffect(() => {
    focusReviewHeading(!busy && step === "review" && hasPreview)
  }, [busy, step, hasPreview])

  useEffect(
    () => () => {
      actionController.current?.abort()
      if (progressToast.current) toast.close(progressToast.current)
      progressToast.current = null
      if (rematch.current) toast.close(`rematch-${rematch.current.occurrence}`)
      rematch.current = null
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
    if (
      error ||
      !sessionJobStatus ||
      !["analyzing", "sorting", "saving", "restoring"].includes(sessionJobStatus)
    )
      return undefined
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    async function poll() {
      try {
        const next = await api<Job | null>("/job", { signal: controller.signal })
        if (controller.signal.aborted) return
        // Follow the single session job even when another playlist takes it over,
        // so this page adapts instead of surfacing a stale state or error.
        setSessionJob(next)
        if (next) skipCleanCheckStep(next)
        if (next) observeRematch(next)
        if (next && isWorking(next)) timer = setTimeout(poll, 1000)
      } catch (err) {
        if (controller.signal.aborted) return
        if (err instanceof ApiError && err.status === 401) {
          window.location.assign("/")
          return
        }
        const message =
          err instanceof Error ? err.message : "We couldn't load progress. Please try again."
        setError(message)
        toast.add({
          id: `playlist-error-${playlist.id}`,
          title: "Couldn't load progress",
          description: message,
          type: "error",
          priority: "high",
          timeout: 0,
          actionProps: { children: "Try again", onClick: () => setError("") },
        })
      }
    }
    timer = setTimeout(poll, 700)
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
    // Status controls the polling lifetime. Each request schedules the next one after it finishes.
  }, [sessionJobStatus, playlist.id, error])

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
                  ? {
                      options: preferences,
                      first_occurrence: firstOccurrence,
                      last_occurrence: lastOccurrence,
                      placements: Object.fromEntries(
                        fixedTracks
                          .filter(
                            (track) =>
                              (placements[track.occurrence] ?? track.original_position) !==
                              track.original_position,
                          )
                          .map((track) => [
                            track.occurrence,
                            placementTargets.get(track.occurrence) ?? 0,
                          ]),
                      ),
                    }
                  : {}),
              }),
      })
      if (controller.signal.aborted) return
      if (action === "analyze" || action === "restore") {
        setFirstOccurrence(null)
        setLastOccurrence(null)
        setPlacements({})
        setStep("check")
        setPreferences(DEFAULT_PREFERENCES)
      }
      if (action === "sort") advanceToReview.current = true
      setSessionJob(next)
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
        title: action === "analyze" ? "Couldn't analyze songs" : "Couldn't start the request",
        description: message,
        type: "error",
        priority: "high",
        timeout: action === "analyze" ? 0 : 8000,
        actionProps:
          action === "analyze"
            ? { children: "Analyze again", onClick: () => void run("analyze") }
            : undefined,
      })
      progressToast.current = null
    } finally {
      if (!controller.signal.aborted) setPending(null)
    }
  }

  const startAnalyzing = useEffectEvent(() => {
    if (!job && !otherJob && playlist.total > 0) void run("analyze")
  })

  const shouldAutoAnalyze = !job && !otherJob && !error && playlist.total > 0
  // PlaylistRoute keys this component by playlist, so this starts once on mount and
  // resumes by itself if another playlist's job was blocking and then finishes.
  useEffect(() => {
    if (!shouldAutoAnalyze) return undefined
    // Let Strict Mode's setup/cleanup pass finish before starting a server job.
    const timer = setTimeout(() => startAnalyzing(), 0)
    return () => clearTimeout(timer)
  }, [shouldAutoAnalyze])

  const placementTargets = new Map<string, number>()
  for (const track of fixedTracks)
    placementTargets.set(
      track.occurrence,
      Math.min(
        Math.max(placements[track.occurrence] ?? track.original_position, 0),
        Math.max(total - 1, 0),
      ),
    )
  const slotTaken = (slot: number, except: Track) =>
    fixedTracks.some(
      (item) =>
        item.occurrence !== except.occurrence && placementTargets.get(item.occurrence) === slot,
    )
  const handlePlacements = (next: Record<string, number>) => {
    setPlacements((current) => (JSON.stringify(current) === JSON.stringify(next) ? current : next))
  }
  const handleApplied = (occurrence: string) => {
    // The rematch polls through the analyzing status; the toast is resolved
    // once polling sees the song leave the working stages.
    advanceToReview.current = false
    rematch.current = { occurrence }
  }
  const showSetup = !!job && !!tracks.length && !analyzing && jobStatus !== "error"

  return (
    <section className="mx-auto max-w-2xl">
      <output className="sr-only">{statusMessage}</output>
      <div className="mb-5 flex min-w-0 items-center justify-between gap-3">
        <Link
          to="/playlists"
          className="inline-flex min-h-8 items-center gap-2 rounded-md text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" strokeWidth={1.5} aria-hidden="true" />
          Your playlists
        </Link>
        <a
          className="inline-flex min-h-8 items-center gap-2 rounded-md text-sm text-muted-foreground transition-colors duration-150 ease-out hover:text-foreground"
          aria-label="Open this playlist in Spotify"
          href={`https://open.spotify.com/playlist/${playlist.id}`}
          target="_blank"
          rel="noreferrer"
        >
          Open Spotify
          <ExternalLink className="size-4" aria-hidden="true" />
        </a>
      </div>
      <div className="flex items-center gap-4">
        {playlist.image ? (
          <img
            src={playlist.image}
            alt=""
            width={64}
            height={64}
            className="size-16 shrink-0 rounded-xl object-cover outline outline-black/10 dark:outline-white/10"
          />
        ) : (
          <div className="flex size-16 shrink-0 items-center justify-center rounded-xl bg-muted">
            <Music2 className="size-7 text-muted-foreground" aria-hidden="true" />
          </div>
        )}
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight wrap-break-word sm:text-3xl">
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
          className="mt-6 rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Alert variant="destructive">
            <AlertDescription>{job.error}</AlertDescription>
          </Alert>
        </div>
      )}

      {error && isWorking(job) && (
        <Button className="mt-5" size="sm" variant="outline" onClick={() => setError("")}>
          Try again
        </Button>
      )}

      {otherJob && !job && (
        <Alert className="mt-8">
          <AlertDescription>
            Another playlist is still being analyzed.
            <Link to={`/playlists/${otherJob.playlist_id}`} className="ml-2 underline">
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

      {!analyzing && !otherJob && (jobStatus === "error" || (!job && error)) && (
        <Button
          className="mt-5"
          onClick={() => void run("analyze")}
          disabled={busy || playlist.total === 0}
        >
          Analyze again
          <ArrowRight aria-hidden="true" />
        </Button>
      )}

      {analyzing && (
        <div className="my-8 rounded-xl border bg-muted/20 p-5 sm:p-6">
          <Progress
            className="items-center gap-y-4"
            value={jobStatus === "analyzing" && job?.total ? job.completed : null}
            max={job?.total || 100}
          >
            <h2>
              <ProgressLabel className="flex items-center gap-2 text-base font-semibold">
                <LoaderCircle className="size-4 motion-safe:animate-spin" aria-hidden="true" />
                {job?.metadata_loaded
                  ? job.total === 1
                    ? "Re-analyzing this song"
                    : "Analyzing songs"
                  : "Loading playlist"}
              </ProgressLabel>
            </h2>
            <ProgressValue className="text-xs">
              {() =>
                jobStatus === "analyzing" && job?.total
                  ? `${job.completed} of ${job.total} analyzed`
                  : "Getting the song list"
              }
            </ProgressValue>
          </Progress>
        </div>
      )}

      {showSetup && step === "check" && (
        <div className="mt-8 border-t pt-6">
          <CheckStep
            tracks={tracks}
            session={session ?? { configured: true, user: null, csrf: null }}
            busy={busy}
            onContinue={() => setStep("preferences")}
            onApplied={handleApplied}
          />
        </div>
      )}

      {showSetup && step === "preferences" && (
        <div className="mt-8 border-t pt-6">
          <PreferencesStep
            preferences={preferences}
            onPreferencesChange={setPreferences}
            busy={busy}
            canSort={canSort}
            choices={choices}
            firstOccurrence={firstOccurrence}
            lastOccurrence={lastOccurrence}
            onFirstChange={setFirstOccurrence}
            onLastChange={setLastOccurrence}
            fixedFirst={fixedFirst}
            fixedLast={fixedLast}
            fixedTracks={fixedTracks}
            total={total}
            placementTargets={placementTargets}
            slotTaken={slotTaken}
            onPlacementsChange={handlePlacements}
            placementConflict={
              pinConflict || placementConflict
                ? (placementConflict ?? "Choose different entries for the first and last songs.")
                : null
            }
            hasPreview={hasPreview}
            onArrange={() => void run("sort")}
          />
        </div>
      )}

      {showSetup && step === "review" && job && hasPreview && (
        <div className="mt-8 border-t pt-6">
          <ReviewStep
            job={job}
            choicesChanged={choicesChanged}
            busy={busy}
            movedCount={movedCount}
            reviewHeading={reviewHeading}
            onSave={() => void run("save")}
            onRestore={() => void run("restore")}
            onAnalyzeAgain={() => void run("analyze")}
            onBack={() => setStep("preferences")}
          />
        </div>
      )}

      {step === "review" && showSetup && job && !hasPreview && (
        <p className="mt-8 text-sm text-muted-foreground">
          There is no preview yet. Go back and arrange the playlist.
        </p>
      )}
    </section>
  )
}
