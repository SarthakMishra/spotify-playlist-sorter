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
  analyzePlaylist,
  ApiError,
  getPreferences,
  restorePreview,
  savePreferences,
  savePreview,
  sortPreview,
  type Job,
  type Options,
  type Playlist,
} from "@/lib/api"
import {
  cancelRematchToast,
  isWorking,
  isWorkingStatus,
  resolveRematchToast,
  watchJob,
} from "@/lib/job"
import {
  fixedAtSlot,
  placementConflict as placementConflictBetween,
  placementOverrides,
  placementsChanged,
} from "@/lib/placement"
import { DEFAULT_PREFERENCES, matchAttention } from "@/lib/preferences"

type StepId = "check" | "preferences" | "review"

function initialStep(job: Job | null): StepId {
  if (job?.sorted_tracks?.length) return "review"
  // Only skip the check step once analysis has finished; mid-analysis every track
  // still looks clean, so deciding then would hide mismatches that appear later.
  if (job?.status === "ready" && job.metadata_loaded) {
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
  // Each playlist owns its job slot; queued analyses wait in the shared worker queue.
  const [job, setJob] = useState<Job | null>(initialJob)
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
  // Flow choices survive a server restart and apply to every future playlist visit.
  const savedPreferences = useRef<Options>(
    initialJob?.options
      ? {
          preset: initialJob.options.preset,
          pace: initialJob.options.pace,
          energy: initialJob.options.energy,
          variety: initialJob.options.variety,
        }
      : DEFAULT_PREFERENCES,
  )
  const actionController = useRef<AbortController | null>(null)
  const progressToast = useRef<string | null>(null)
  const reviewHeading = useRef<HTMLHeadingElement>(null)
  const errorRegion = useRef<HTMLDivElement>(null)
  const actionFocus = useRef<{ element: Element | null; failed: boolean } | null>(null)
  const advanceToReview = useRef(false)
  const rematches = useRef<Set<string>>(new Set())
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
  // Batched recording rematches stay inside the check step; only fresh analyses
  // take over the page with the analyzing banner.
  const analyzing = (pending === "analyze" || jobStatus === "analyzing") && !job?.rematching
  // A queued analysis has no song list yet; its position is the queue line it waits in.
  const queued =
    jobStatus === "analyzing" &&
    !job?.metadata_loaded &&
    job?.queue_position != null &&
    !job.stale &&
    !job.rematching
  const tracks = job?.tracks ?? []
  const choices = tracks.filter(
    (track) => track.analysis_status === "ready" && track.fixed_reason === null,
  )
  const canSort = choices.length >= 2
  const total = tracks.length
  const fixedTracks = tracks.filter((track) => track.fixed_reason)
  const attentionCount = tracks.filter((track) => matchAttention(track) !== null).length
  const fixedFirst = fixedAtSlot(fixedTracks, placements, 0)
  const fixedLast = fixedAtSlot(fixedTracks, placements, total - 1)
  const hasPreview = !!job?.sorted_tracks.length && job.status !== "error"
  const conflicts = placementConflictBetween(
    fixedTracks,
    placements,
    total,
    firstOccurrence,
    lastOccurrence,
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
      placementsChanged(fixedTracks, placements, job.placements))
  const movedCount =
    hasPreview && job
      ? job.sorted_tracks.filter((track, index) => track.original_position !== index).length
      : 0

  const statusMessage = queued
    ? `Waiting in queue. Position ${job?.queue_position}.`
    : job?.rematching
      ? "Re-analyzing the recordings you picked. Other songs stay available."
      : analyzing
        ? job?.stale
          ? "This playlist changed since its last analysis. Waiting for a fresh analysis."
          : job?.metadata_loaded
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
                : job?.stored
                  ? "Restored from a previous analysis. Re-analyze to make changes."
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

  const observeRematch = useEffectEvent((next: Job) => {
    if (next.playlist_id !== playlist.id) return
    for (const occurrence of rematches.current) {
      if (resolveRematchToast(next, occurrence)) rematches.current.delete(occurrence)
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
      for (const occurrence of rematches.current) cancelRematchToast(occurrence)
      rematches.current.clear()
    },
    [],
  )

  useEffect(() => {
    if (!error) return undefined
    return () => toast.close(`playlist-error-${playlist.id}`)
  }, [error, playlist.id])

  // A fresh visit prefills the choices this listener arranged with last time; a job
  // in progress keeps the choices it was started with.
  useEffect(() => {
    if (initialJob?.options) return
    getPreferences()
      .then((saved) => {
        savedPreferences.current = saved
        setPreferences((current) => (current === DEFAULT_PREFERENCES ? { ...saved } : current))
      })
      .catch(() => undefined)
  }, [initialJob])

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
    if (error || !isWorkingStatus(jobStatus)) return undefined
    return watchJob(playlist.id, {
      onJob: (next) => {
        setJob(next)
        if (next) skipCleanCheckStep(next)
        if (next) observeRematch(next)
      },
      onError: (err) => {
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
      },
    })
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
    try {
      const next =
        action === "analyze"
          ? await analyzePlaylist(playlist.id, { signal: controller.signal })
          : action === "sort"
            ? await sortPreview(
                playlist.id,
                {
                  revision: job?.revision ?? "",
                  options: preferences,
                  first_occurrence: firstOccurrence,
                  last_occurrence: lastOccurrence,
                  placements: placementOverrides(fixedTracks, placements, total),
                },
                { signal: controller.signal },
              )
            : action === "save"
              ? await savePreview(playlist.id, job?.revision ?? "", { signal: controller.signal })
              : await restorePreview(playlist.id, job?.revision ?? "", {
                  signal: controller.signal,
                })
      if (controller.signal.aborted) return
      if (action === "analyze" || action === "restore") {
        setFirstOccurrence(null)
        setLastOccurrence(null)
        setPlacements({})
        setStep("check")
        setPreferences({ ...savedPreferences.current })
      }
      if (action === "sort") {
        advanceToReview.current = true
        savedPreferences.current = preferences
        savePreferences(preferences).catch(() => undefined)
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
    if (!job || job.stale) void run("analyze")
  })

  const shouldAutoAnalyze = (!job || job.stale) && !error && playlist.total > 0
  // PlaylistRoute keys this component by playlist, so this starts once on mount and
  // resumes by itself if another playlist's job was blocking and then finishes.
  useEffect(() => {
    if (!shouldAutoAnalyze) return undefined
    // Let Strict Mode's setup/cleanup pass finish before starting a server job.
    const timer = setTimeout(() => startAnalyzing(), 0)
    return () => clearTimeout(timer)
  }, [shouldAutoAnalyze])

  const handlePlacements = (next: Record<string, number>) => {
    setPlacements((current) => (JSON.stringify(current) === JSON.stringify(next) ? current : next))
  }
  const handleApplied = (occurrence: string, updated: Job) => {
    // Each rematch polls through the analyzing status; its toast is resolved once
    // polling sees that song leave the working stages.
    advanceToReview.current = false
    rematches.current.add(occurrence)
    setJob(updated)
  }
  // A stored revisit serves true results but no live playlist data; every action
  // needs a fresh analysis, so the interactive steps must not present dead buttons.
  const showSetup =
    !!job && !!tracks.length && !analyzing && !job.stale && !job.stored && jobStatus !== "error"

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

      {!analyzing && job?.stored && (
        <Alert className="mt-8">
          <AlertDescription>
            This analysis was restored from a previous visit. Re-analyze to check recordings and
            make changes.
          </AlertDescription>
        </Alert>
      )}

      {!analyzing && job?.stored && (
        <Button
          className="mt-5"
          onClick={() => void run("analyze")}
          disabled={busy || playlist.total === 0}
        >
          Analyze again
          <ArrowRight aria-hidden="true" />
        </Button>
      )}

      {(!job && playlist.total === 0) || (jobStatus === "ready" && !tracks.length) ? (
        <p className="mt-8 text-sm text-muted-foreground">
          This playlist is empty. Add some songs on Spotify first.
        </p>
      ) : null}

      {!analyzing && (jobStatus === "error" || (!job && error)) && (
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
                {queued
                  ? "Waiting in queue"
                  : job?.metadata_loaded
                    ? job.total === 1
                      ? "Re-analyzing this song"
                      : "Analyzing songs"
                    : "Loading playlist"}
              </ProgressLabel>
            </h2>
            <ProgressValue className="text-xs">
              {() =>
                queued
                  ? `Position ${job?.queue_position}`
                  : jobStatus === "analyzing" && job?.total
                    ? `${job.completed} of ${job.total} analyzed`
                    : "Getting the song list"
              }
            </ProgressValue>
          </Progress>
          {queued && (
            <p className="mt-4 text-sm text-muted-foreground">
              This playlist changed since its last analysis. New songs need a fresh analysis first.
            </p>
          )}
          <Button variant="outline" size="sm" render={<Link to="/queue" />} className="mt-4">
            See the queue
          </Button>
        </div>
      )}

      {showSetup && step === "check" && (
        <div className="mt-8 border-t pt-6">
          <CheckStep
            playlistId={playlist.id}
            tracks={tracks}
            busy={busy && !job?.rematching}
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
            attentionCount={attentionCount}
            placements={placements}
            onPlacementsChange={handlePlacements}
            placementConflict={conflicts}
            hasPreview={hasPreview}
            onArrange={() => void run("sort")}
            onCheckTracks={() => setStep("check")}
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
