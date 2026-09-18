import { Fragment, Suspense, lazy } from "react"
import { CircleAlert } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableMarkerRow,
  TableRow,
  TableHeader,
} from "@/components/ui/table"
import { cn } from "cn"
import { StatusBadge } from "@/components/steps/check-step"
import type { Job, ReviewHighlight, Track } from "@/lib/api"
import { measuredIntensity, intensityLabel } from "@/lib/review"

const SongDetails = lazy(() => import("@/components/song-details"))
const SlopeGraph = lazy(() => import("@/components/slope-graph"))

// Warm the lazily loaded details chunks before their sections are opened.
const preloadSongDetails = () => {
  void import("@/components/song-details")
}
const preloadSlopeGraph = () => {
  void import("@/components/slope-graph")
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

export function ReviewStep({
  job,
  choicesChanged,
  busy,
  movedCount,
  reviewHeading,
  onSave,
  onRestore,
  onAnalyzeAgain,
  onBack,
}: {
  job: Job
  choicesChanged: boolean
  busy: boolean
  movedCount: number
  reviewHeading: React.RefObject<HTMLHeadingElement | null>
  onSave: () => void
  onRestore: () => void
  onAnalyzeAgain: () => void
  onBack: () => void
}) {
  const showNotes = job.status !== "restored" && !choicesChanged
  return (
    <section className="space-y-5" aria-labelledby="review-heading">
      <div className="min-w-0">
        <h2
          ref={reviewHeading}
          id="review-heading"
          tabIndex={-1}
          className="rounded-sm text-lg font-semibold outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {job.status === "restored" ? "Restored order" : "Playlist preview"}
        </h2>
        {(job.status !== "ready" || choicesChanged || job.arrangement?.unchanged) && (
          <p aria-live="polite" className="mt-1 text-sm text-muted-foreground">
            {job.status === "restored"
              ? "Previous order restored and verified on Spotify."
              : job.status === "saved"
                ? "Saved and verified on Spotify."
                : choicesChanged
                  ? "Arrange again to apply your choices."
                  : job.arrangement?.unchanged
                    ? "This is already your saved order."
                    : ""}
          </p>
        )}
        {showNotes && !job.arrangement?.unchanged && <VerdictLine job={job} />}
      </div>
      {job.can_restore && (
        <div className="space-y-2">
          <Button
            variant="outline"
            onClick={onRestore}
            disabled={busy}
            aria-describedby="restore-limit"
          >
            Restore previous order
          </Button>
          <p id="restore-limit" className="text-xs leading-5 text-muted-foreground">
            Undoes your most recent save in this session, if Spotify is still unchanged. Analyzing a
            playlist again, signing out, session expiry or a server restart removes this option.
          </p>
        </div>
      )}
      {showNotes && job.arrangement?.limited && (
        <p className="text-sm text-muted-foreground">
          This playlist is too large for a full search. Your first and last song choices were
          applied; the other songs keep their original relative order.
        </p>
      )}
      <SongList
        tracks={job.sorted_tracks}
        label={job.status === "restored" ? "Restored song order" : "Suggested song order"}
        highlights={showNotes ? (job.review?.highlights ?? []) : []}
      />
      {showNotes && (
        <div className="space-y-3">
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
                  original={job.tracks}
                  tracks={job.sorted_tracks}
                  transitions={job.transitions}
                />
              </Suspense>
            </div>
          </details>
        </div>
      )}
      <div className="space-y-3">
        {!(job.status === "saved" || job.status === "restored" || job.arrangement?.unchanged) && (
          <Button size="lg" className="w-full" onClick={onSave} disabled={busy || choicesChanged}>
            Save to Spotify
          </Button>
        )}
        {job.kept_count > 0 && (
          <Button variant="outline" className="w-full" disabled={busy} onClick={onAnalyzeAgain}>
            Analyze songs again
          </Button>
        )}
        <Button variant="outline" className="w-full" onClick={onBack} disabled={busy}>
          Adjust preferences
        </Button>
      </div>
    </section>
  )
}
