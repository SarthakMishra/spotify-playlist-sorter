import { useEffect, useRef, useState } from "react"
import {
  CircleAlert,
  CircleCheck,
  CircleX,
  Clock,
  LoaderCircle,
  type LucideIcon,
} from "lucide-react"
import { cn } from "cn"
import { Button } from "@/components/ui/button"
import { MatchFixDialog } from "@/components/match-fix-dialog"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { Session, Track } from "@/lib/api"
import { matchAttention } from "@/lib/preferences"

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

export function StatusBadge({
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

function MatchRow({
  track,
  attention,
  session,
  disabled,
  onApplied,
}: {
  track: Track
  attention: "fix" | "check" | null
  session: Session
  disabled: boolean
  onApplied: (occurrence: string) => void
}) {
  const [fixing, setFixing] = useState(false)
  return (
    <li className="flex flex-wrap items-center gap-3 py-3">
      <StatusBadge status={track.analysis_status} reason={track.fixed_reason} />
      <div className="min-w-0 flex-1 basis-40">
        <p className="truncate text-sm font-medium">{track.name}</p>
        <p className="truncate text-xs text-muted-foreground">
          {track.artist}
          {track.recording?.channel && <> · {track.recording.channel}</>}
        </p>
      </div>
      {attention && track.id && (
        <Button variant="outline" size="sm" onClick={() => setFixing(true)} disabled={disabled}>
          {attention === "fix" ? "Fix recording" : "Check recording"}
        </Button>
      )}
      <MatchFixDialog
        key={fixing ? "open" : "closed"}
        track={track}
        session={session}
        open={fixing}
        onOpenChange={setFixing}
        onApplied={onApplied}
      />
    </li>
  )
}

export function CheckStep({
  tracks,
  session,
  busy,
  onContinue,
  onApplied,
}: {
  tracks: Track[]
  session: Session
  busy: boolean
  onContinue: () => void
  onApplied: (occurrence: string) => void
}) {
  const noted = tracks.filter((track) => matchAttention(track) !== null)
  const [issuesOnly, setIssuesOnly] = useState(noted.length > 0)
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    heading.current?.focus()
  }, [])
  const shown = issuesOnly ? noted : tracks
  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h2
            ref={heading}
            id="check-heading"
            tabIndex={-1}
            className="rounded-sm text-lg font-semibold outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            Check songs
          </h2>
          <p aria-live="polite" className="mt-1 text-sm text-muted-foreground">
            {noted.length === 0
              ? "Every song found a confident recording match."
              : noted.length === 1
                ? "1 song needs a look before arranging."
                : `${noted.length} songs need a look before arranging.`}
          </p>
        </div>
        {noted.length > 0 && (
          <ToggleGroup
            value={[issuesOnly ? "issues" : "all"]}
            onValueChange={(values: unknown[]) => {
              const next = values[0]
              if (next === "issues" || next === "all") setIssuesOnly(next === "issues")
            }}
            aria-label="Which songs to show"
          >
            <ToggleGroupItem value="issues" size="sm">
              Issues
            </ToggleGroupItem>
            <ToggleGroupItem value="all" size="sm">
              All songs
            </ToggleGroupItem>
          </ToggleGroup>
        )}
      </div>
      <ul className="divide-y">
        {shown.map((track) => (
          <MatchRow
            key={track.occurrence}
            track={track}
            attention={matchAttention(track)}
            session={session}
            disabled={busy}
            onApplied={onApplied}
          />
        ))}
      </ul>
      <div className="flex items-center gap-3">
        <Button onClick={onContinue} disabled={busy} size="lg" className="min-w-0 flex-1">
          {noted.some((track) => matchAttention(track) === "fix") ? "Continue anyway" : "Continue"}
        </Button>
      </div>
    </section>
  )
}
