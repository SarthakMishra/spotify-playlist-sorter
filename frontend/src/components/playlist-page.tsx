import { Fragment, Suspense, lazy, useEffect, useEffectEvent, useRef, useState } from "react"
import { Link, useLoaderData, useParams, useRouteLoaderData } from "react-router"
import {
  ArrowDownWideNarrow,
  ArrowLeft,
  ArrowRight,
  CircleAlert,
  CircleCheck,
  CircleX,
  Clock,
  ExternalLink,
  LoaderCircle,
  Music2,
  type LucideIcon,
} from "lucide-react"
import { cn } from "cn"
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { toast } from "@/components/ui/toast"
import {
  Table,
  TableHeader,
  TableHead,
  TableRow,
  TableMarkerRow,
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
  type ReviewHighlight,
  type Session,
  type Track,
} from "@/lib/api"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { measuredIntensity, intensityLabel } from "@/lib/review"

const SongDetails = lazy(() => import("@/components/song-details"))
const SlopeGraph = lazy(() => import("@/components/slope-graph"))

// Warm the recharts-heavy details chunk before the details section is opened.
const preloadSongDetails = () => {
  void import("@/components/song-details")
}
const preloadSlopeGraph = () => {
  void import("@/components/slope-graph")
}

type PlacementChoice = "keep" | "top" | "bottom" | "custom"

const placementItems: { value: PlacementChoice; label: string }[] = [
  { value: "keep", label: "Keep in place" },
  { value: "top", label: "Move to top" },
  { value: "bottom", label: "Move to bottom" },
  { value: "custom", label: "Custom position" },
]

const groupPlacementItems: { value: "keep" | "top" | "bottom"; label: string }[] = [
  { value: "keep", label: "Keep in place" },
  { value: "top", label: "Move to top" },
  { value: "bottom", label: "Move to bottom" },
]

type StatusTone = "success" | "warning" | "failed" | "analyzing"

const toneClass: Record<StatusTone, string> = {
  success: "bg-success/15 text-success",
  warning: "bg-warning/15 text-warning",
  failed: "bg-destructive/15 text-destructive",
  analyzing: "bg-foreground/10 text-muted-foreground",
}

const statusMeta: Record<
  Track["analysis_status"],
  { label: string; tone: StatusTone; icon: LucideIcon }
> = {
  pending: { label: "Waiting to analyze", tone: "warning", icon: Clock },
  matching: { label: "Finding recording", tone: "analyzing", icon: LoaderCircle },
  downloading: { label: "Downloading audio", tone: "analyzing", icon: LoaderCircle },
  analyzing: { label: "Measuring audio", tone: "analyzing", icon: LoaderCircle },
  ready: { label: "Analyzed", tone: "success", icon: CircleCheck },
  uncertain: { label: "Recording uncertain", tone: "failed", icon: CircleAlert },
  error: { label: "Analysis failed", tone: "failed", icon: CircleX },
  fixed: { label: "Can't analyze", tone: "failed", icon: CircleX },
}

function StatusBadge({
  status,
  reason,
}: {
  status: Track["analysis_status"]
  reason: string | null
}) {
  const meta = statusMeta[status]
  const label = reason ? `${meta.label} · ${reason}` : meta.label
  const Icon = meta.icon
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <span
            aria-label={label}
            className={cn(
              "inline-flex size-7 items-center justify-center rounded-full",
              toneClass[meta.tone],
            )}
          />
        }
      >
        <Icon
          className={cn("size-4", meta.tone === "analyzing" && "motion-safe:animate-spin")}
          aria-hidden="true"
        />
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )
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

function VerdictLine({ job }: { job: Job }) {
  const moved = job.sorted_tracks.filter(
    (track, index) => track.original_position + 1 !== index + 1,
  ).length
  const review = job.review
  const highlightCount = review?.highlights.length ?? 0
  const assessed = review?.suggested_assessed
  const parts: string[] = [
    moved === 0
      ? "No songs moved."
      : `${moved} of ${job.sorted_tracks.length} ${moved === 1 ? "song" : "songs"} moved.`,
  ]
  if (assessed != null && assessed > 0)
    parts.push(
      highlightCount > 0
        ? `${highlightCount} ${highlightCount === 1 ? "transition" : "transitions"} worth checking.`
        : "No rough transitions found.",
    )
  return <p className="mt-2 text-sm text-muted-foreground tabular-nums">{parts.join(" ")}</p>
}

function IntensityCell({ track }: { track: Track }) {
  const intensity = measuredIntensity(track)
  const label = intensityLabel(intensity)
  if (intensity === null)
    return (
      <span className="text-xs text-muted-foreground/40" aria-label="Intensity unavailable">
        —
      </span>
    )
  return (
    <span className="flex items-center gap-1.5" aria-label={`Intensity: ${label}`}>
      <span
        aria-hidden="true"
        className={cn(
          "inline-block size-2 rounded-full",
          intensity < 1 / 3
            ? "bg-foreground/30"
            : intensity < 2 / 3
              ? "bg-foreground/60"
              : "bg-foreground",
        )}
      />
      <span className="text-xs text-muted-foreground">{label}</span>
    </span>
  )
}

function TransitionMarker({ note }: { note: ReviewHighlight }) {
  return (
    <TableMarkerRow>
      <TableCell
        colSpan={5}
        aria-label={`Transition note between ${note.track1_name} and ${note.track2_name}: ${note.text}`}
        className="py-2 pr-3 pl-9"
      >
        <p className="flex items-start gap-2.5 text-xs leading-5 text-muted-foreground">
          <CircleAlert className="mt-0.5 size-3.5 shrink-0 text-warning" aria-hidden="true" />
          <span className="min-w-0">
            <span className="font-medium text-foreground">
              {note.track1_name} → {note.track2_name}
            </span>
            <span className="mx-1.5 text-muted-foreground/60" aria-hidden="true">
              ·
            </span>
            {note.text}
          </span>
        </p>
      </TableCell>
    </TableMarkerRow>
  )
}

function SongList({
  tracks,
  label,
  highlights,
}: {
  tracks: Track[]
  label: string
  highlights: ReviewHighlight[]
}) {
  const notesBefore = new Map<string, ReviewHighlight[]>()
  const endNotes: ReviewHighlight[] = []
  for (const note of highlights) {
    const existing = notesBefore.get(note.track2_occurrence)
    if (existing) existing.push(note)
    else if (tracks.some((track) => track.occurrence === note.track2_occurrence))
      notesBefore.set(note.track2_occurrence, [note])
    else endNotes.push(note)
  }
  return (
    <Table className="table-fixed" scrollLabel={label}>
      <TableCaption className="sr-only">{label}</TableCaption>
      <TableHeader>
        <TableRow>
          <TableHead className="w-12">#</TableHead>
          <TableHead>Song</TableHead>
          <TableHead className="w-20">
            <span className="sr-only">Intensity</span>
          </TableHead>
          <TableHead className="w-20 text-right">Was</TableHead>
          <TableHead className="w-14">
            <span className="sr-only">Analysis status</span>
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {tracks.map((track, index) => {
          const position = index + 1
          const was = track.original_position + 1
          const moved = was !== position
          const before = notesBefore.get(track.occurrence) ?? []
          return (
            <Fragment key={track.occurrence}>
              {before.map((note) => (
                <TransitionMarker key={note.track1_occurrence} note={note} />
              ))}
              <TableRow>
                <TableCell className="py-2.5 align-top text-muted-foreground tabular-nums">
                  {position}
                </TableCell>
                <TableCell className="py-2.5 whitespace-normal">
                  <p className="font-medium wrap-break-word">{track.name}</p>
                  <p className="mt-0.5 wrap-break-word text-muted-foreground">{track.artist}</p>
                </TableCell>
                <TableCell className="py-2.5 align-top">
                  <IntensityCell track={track} />
                </TableCell>
                <TableCell className="py-2.5 text-right align-top tabular-nums">
                  {moved ? (
                    <span className="text-xs text-muted-foreground">#{was}</span>
                  ) : (
                    <span className="text-xs text-muted-foreground/40">—</span>
                  )}
                </TableCell>
                <TableCell className="py-2.5 text-right align-top">
                  <StatusBadge status={track.analysis_status} reason={track.fixed_reason} />
                </TableCell>
              </TableRow>
            </Fragment>
          )
        })}
        {endNotes.map((note) => (
          <TransitionMarker key={note.track1_occurrence} note={note} />
        ))}
      </TableBody>
    </Table>
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
  // The session holds a single job slot, whichever playlist it owns. Polling keeps it
  // fresh so blocked states clear as soon as the working job finishes.
  const [sessionJob, setSessionJob] = useState<Job | null>(initialJob)
  const job = sessionJob?.playlist_id === playlist.id ? sessionJob : null
  const [error, setError] = useState("")
  const [pending, setPending] = useState<"analyze" | "sort" | "save" | "restore" | null>(null)
  const [profile, setProfile] = useState<Profile>(job?.profile ?? "smooth")
  const [firstOccurrence, setFirstOccurrence] = useState<string | null>(
    job?.first_occurrence ?? null,
  )
  const [lastOccurrence, setLastOccurrence] = useState<string | null>(job?.last_occurrence ?? null)
  const [placementChoice, setPlacementChoice] = useState<Record<string, PlacementChoice>>({})
  const [customPositions, setCustomPositions] = useState<Record<string, number>>({})
  const [placementMode, setPlacementMode] = useState<"all" | "individual">("all")
  const [defaultPlacement, setDefaultPlacement] = useState<"keep" | "top" | "bottom">("keep")
  const actionController = useRef<AbortController | null>(null)
  const progressToast = useRef<string | null>(null)
  const reviewHeading = useRef<HTMLHeadingElement>(null)
  const errorRegion = useRef<HTMLDivElement>(null)
  const actionFocus = useRef<{ element: Element | null; failed: boolean } | null>(null)
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
  const showSetup = !!job && !!tracks.length && !analyzing && job.status !== "error"
  const placementTargets = new Map<string, number>()
  if (placementMode === "all") {
    fixedTracks.forEach((track, index) => {
      if (defaultPlacement === "top") placementTargets.set(track.occurrence, index)
      else if (defaultPlacement === "bottom")
        placementTargets.set(track.occurrence, total - fixedTracks.length + index)
      else placementTargets.set(track.occurrence, track.original_position)
    })
  } else {
    for (const track of fixedTracks) {
      const choice = placementChoice[track.occurrence] ?? defaultPlacement
      if (choice === "top") placementTargets.set(track.occurrence, 0)
      else if (choice === "bottom") placementTargets.set(track.occurrence, total - 1)
      else if (choice === "custom") {
        const position = customPositions[track.occurrence] ?? track.original_position + 1
        placementTargets.set(
          track.occurrence,
          Math.min(Math.max(position, 1), Math.max(total, 1)) - 1,
        )
      } else placementTargets.set(track.occurrence, track.original_position)
    }
  }
  function targetFor(track: Track): number {
    return placementTargets.get(track.occurrence) ?? track.original_position
  }
  const slotTaken = (slot: number, except: Track) =>
    fixedTracks.some((item) => item.occurrence !== except.occurrence && targetFor(item) === slot)
  const fixedFirst = fixedTracks.find((track) => targetFor(track) === 0) ?? null
  const fixedLast = fixedTracks.find((track) => targetFor(track) === total - 1) ?? null
  const pinConflict = firstOccurrence !== null && firstOccurrence === lastOccurrence
  const duplicatePlacement = fixedTracks.find((track, index) =>
    fixedTracks.some(
      (other, otherIndex) => otherIndex !== index && targetFor(other) === targetFor(track),
    ),
  )
  const placementConflict = duplicatePlacement
    ? `Position ${targetFor(duplicatePlacement) + 1} is used by more than one item. Choose different positions.`
    : null
  const hasPreview = !!job?.sorted_tracks.length && job.status !== "error"
  const placementsChanged =
    hasPreview &&
    fixedTracks.some(
      (track) => targetFor(track) !== (job.placements[track.occurrence] ?? track.original_position),
    )
  const choicesChanged =
    hasPreview &&
    (profile !== job?.profile ||
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
    else if (hasPreview) reviewHeading.current?.focus()
  }, [busy, hasPreview, jobStatus])

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
                      profile,
                      first_occurrence: firstOccurrence,
                      last_occurrence: lastOccurrence,
                      placements: Object.fromEntries(
                        fixedTracks
                          .filter((track) => targetFor(track) !== track.original_position)
                          .map((track) => [track.occurrence, targetFor(track)]),
                      ),
                    }
                  : {}),
              }),
      })
      if (controller.signal.aborted) return
      if (action === "analyze" || action === "restore") {
        setFirstOccurrence(null)
        setLastOccurrence(null)
        setPlacementChoice({})
        setCustomPositions({})
        setPlacementMode("all")
        setDefaultPlacement("keep")
      }
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

  return (
    <section className="mx-auto max-w-2xl">
      <output className="sr-only">{statusMessage}</output>
      <Link
        to="/playlists"
        className="mb-5 inline-flex min-h-8 items-center gap-2 rounded-md text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" strokeWidth={1.5} aria-hidden="true" />
        Your playlists
      </Link>
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
          className="mt-7 rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
                {job?.metadata_loaded ? "Analyzing songs" : "Loading playlist"}
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

      {showSetup && (
        <div className="mt-8 border-t pt-6">
          {canSort ? (
            <div className="space-y-6">
              <fieldset disabled={busy}>
                <legend className="text-sm font-medium">Listening style</legend>
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
                    This item is placed first. {fixedFirst.fixed_reason}.
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
                    This item is placed last. {fixedLast.fixed_reason}.
                  </p>
                )}
              </div>
              {fixedTracks.length > 0 && (
                <fieldset disabled={busy}>
                  <legend className="flex items-center gap-2 text-sm font-medium">
                    Items that can't be analyzed
                    <span className="inline-flex min-w-5 items-center justify-center rounded-full bg-muted px-1.5 py-0.5 text-xs font-normal text-muted-foreground tabular-nums">
                      {fixedTracks.length}
                    </span>
                  </legend>
                  {placementMode === "all" ? (
                    <div className="mt-3 flex animate-in flex-wrap items-center gap-x-3 gap-y-2 duration-150 ease-out fade-in-0">
                      <Select
                        items={groupPlacementItems}
                        value={defaultPlacement}
                        onValueChange={(value) => {
                          if (value === null) return
                          setDefaultPlacement(value)
                        }}
                      >
                        <SelectTrigger
                          size="sm"
                          className="min-w-40 flex-1"
                          aria-label="Placement for items that can't be analyzed"
                        >
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="keep">Keep in place</SelectItem>
                          <SelectItem value="top">Move to top</SelectItem>
                          <SelectItem value="bottom">Move to bottom</SelectItem>
                        </SelectContent>
                      </Select>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setPlacementMode("individual")}
                      >
                        Choose individually
                      </Button>
                    </div>
                  ) : (
                    <div className="mt-3 animate-in duration-150 ease-out fade-in-0">
                      <ul className="divide-y">
                        {fixedTracks.map((track) => {
                          const choice = placementChoice[track.occurrence] ?? defaultPlacement
                          const custom =
                            customPositions[track.occurrence] ?? track.original_position + 1
                          return (
                            <li
                              key={track.occurrence}
                              className="flex flex-wrap items-center gap-3 py-3.5"
                            >
                              <div className="min-w-0 flex-1 basis-40">
                                <p className="truncate text-sm font-medium">{track.name}</p>
                                <p className="truncate text-xs text-muted-foreground">
                                  {track.fixed_reason} · Currently #{track.original_position + 1}
                                </p>
                              </div>
                              <div className="flex items-center gap-2">
                                <Select
                                  items={placementItems}
                                  value={choice}
                                  onValueChange={(value) => {
                                    if (value === null) return
                                    setPlacementChoice((current) => ({
                                      ...current,
                                      [track.occurrence]: value,
                                    }))
                                    if (value === "top" || (value === "custom" && custom === 1))
                                      setFirstOccurrence(null)
                                    if (
                                      value === "bottom" ||
                                      (value === "custom" && custom === total)
                                    )
                                      setLastOccurrence(null)
                                  }}
                                >
                                  <SelectTrigger
                                    size="sm"
                                    className="min-w-40"
                                    aria-label={`Position for ${track.name}`}
                                  >
                                    <SelectValue />
                                  </SelectTrigger>
                                  <SelectContent>
                                    <SelectItem value="keep">Keep in place</SelectItem>
                                    <SelectItem value="top" disabled={slotTaken(0, track)}>
                                      Move to top
                                    </SelectItem>
                                    <SelectItem
                                      value="bottom"
                                      disabled={slotTaken(total - 1, track)}
                                    >
                                      Move to bottom
                                    </SelectItem>
                                    <SelectItem value="custom">Custom position</SelectItem>
                                  </SelectContent>
                                </Select>
                                {choice === "custom" && (
                                  <input
                                    type="number"
                                    className="w-16 animate-in rounded-lg border bg-background px-2 py-1 text-sm tabular-nums duration-150 ease-out fade-in-0 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 focus-visible:outline-none disabled:opacity-50"
                                    min={1}
                                    max={total}
                                    value={custom}
                                    aria-label={`Custom position for ${track.name}`}
                                    onChange={(event) => {
                                      const position = Number.parseInt(event.target.value, 10)
                                      if (Number.isNaN(position)) return
                                      const bounded = Math.min(Math.max(position, 1), total)
                                      setCustomPositions((current) => ({
                                        ...current,
                                        [track.occurrence]: bounded,
                                      }))
                                      if (bounded === 1) setFirstOccurrence(null)
                                      if (bounded === total) setLastOccurrence(null)
                                    }}
                                  />
                                )}
                              </div>
                            </li>
                          )
                        })}
                      </ul>
                      <Button
                        variant="outline"
                        size="sm"
                        className="mt-3"
                        onClick={() => {
                          setPlacementMode("all")
                          setPlacementChoice({})
                          setCustomPositions({})
                        }}
                      >
                        Use the same position for all
                      </Button>
                    </div>
                  )}
                </fieldset>
              )}
              {(pinConflict || placementConflict) && (
                <p role="alert" className="text-sm text-destructive">
                  {placementConflict ?? "Choose different entries for the first and last songs."}
                </p>
              )}
              <div className="pt-2">
                <Button
                  variant={hasPreview ? "outline" : "default"}
                  onClick={() => void run("sort")}
                  disabled={busy || pinConflict || placementConflict !== null}
                >
                  <ArrowDownWideNarrow aria-hidden="true" />
                  {hasPreview ? "Arrange again" : "Arrange playlist"}
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                {choices.length === 0
                  ? "None of these songs could be analyzed. Your playlist stays in its original order."
                  : "Only one song can move. At least two analyzed songs are needed to rearrange this playlist."}
              </p>
              <Button variant="outline" onClick={() => void run("analyze")} disabled={busy}>
                Analyze again
              </Button>
            </div>
          )}
        </div>
      )}
      {job?.status === "error" && !!tracks.length && (
        <p className="mt-5 text-sm text-muted-foreground">
          This is the order last loaded. Analyze again to see the current Spotify playlist.
        </p>
      )}
      {hasPreview && job && (
        <>
          <div className="mt-8 border-t pt-6" aria-hidden="true" />
          <div className="space-y-4">
            <div className="min-w-0">
              <h2
                ref={reviewHeading}
                tabIndex={-1}
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
              {job.status !== "restored" && !choicesChanged && !job.arrangement?.unchanged && (
                <VerdictLine job={job} />
              )}
            </div>
            {job.can_restore && (
              <div className="space-y-2">
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
                  Analyzing a playlist again, signing out, session expiry or a server restart
                  removes this option.
                </p>
              </div>
            )}
            {hasPreview && !choicesChanged && job.arrangement?.limited && (
              <p className="text-sm text-muted-foreground">
                This playlist is too large for a full search. Your first and last song choices were
                applied; the other songs keep their original relative order.
              </p>
            )}
            <SongList
              tracks={job.sorted_tracks}
              label={job.status === "restored" ? "Restored song order" : "Suggested song order"}
              highlights={
                job.status !== "restored" && !choicesChanged ? (job.review?.highlights ?? []) : []
              }
            />
            {job.status !== "restored" && !choicesChanged && (
              <div className="space-y-3">
                {job.arrangement?.same_as_other_profile && (
                  <p className="text-sm text-muted-foreground">
                    Both styles found the same order with these song choices.
                  </p>
                )}
                {movedCount > 0 && (
                  <details className="rounded-xl border p-4">
                    <summary
                      onMouseEnter={preloadSlopeGraph}
                      onFocus={preloadSlopeGraph}
                      className="cursor-pointer rounded-sm text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring"
                    >
                      What moved
                    </summary>
                    <div className="mt-4 space-y-6">
                      <Suspense
                        fallback={
                          <output className="block py-5 text-sm text-muted-foreground">
                            Loading chart...
                          </output>
                        }
                      >
                        <SlopeGraph tracks={job.sorted_tracks} />
                      </Suspense>
                    </div>
                  </details>
                )}
                <details className="rounded-xl border p-4">
                  <summary
                    onMouseEnter={preloadSongDetails}
                    onFocus={preloadSongDetails}
                    className="cursor-pointer rounded-sm text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring"
                  >
                    Details
                  </summary>
                  <div className="mt-4 space-y-6">
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
                  </div>
                </details>
              </div>
            )}
          </div>
          <div className="mt-6 space-y-3">
            {job.status === "saved" || job.status === "restored" || job.arrangement?.unchanged ? (
              <a
                className={buttonVariants({
                  variant: "outline",
                  size: "lg",
                  className: "w-full",
                })}
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
                size="lg"
                className="w-full"
                onClick={() => void run("save")}
                disabled={busy || choicesChanged || pinConflict}
              >
                Save to Spotify
              </Button>
            )}
            {job.kept_count > 0 && (
              <Button
                variant="outline"
                className="w-full"
                disabled={busy}
                onClick={() => void run("analyze")}
              >
                Analyze songs again
              </Button>
            )}
          </div>
        </>
      )}
    </section>
  )
}
