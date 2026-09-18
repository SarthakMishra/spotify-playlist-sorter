import { useEffect, useMemo, useState } from "react"
import { CircleAlert, ExternalLink, Play, Search } from "lucide-react"
import { cn } from "cn"
import { Badge } from "@/components/ui/badge"
import { Button, buttonVariants } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Spinner } from "@/components/ui/spinner"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { toast } from "@/components/ui/toast"
import { api, type Candidate, type Session, type Track } from "@/lib/api"
import { elapsedTime } from "@/lib/review"

export function MatchFixDialog({
  track,
  session,
  open,
  onOpenChange,
  onApplied,
}: {
  track: Track
  session: Session
  open: boolean
  onOpenChange: (open: boolean) => void
  onApplied: (occurrence: string) => void
}) {
  const [candidates, setCandidates] = useState<Candidate[] | null>(null)
  const [error, setError] = useState("")
  const [filter, setFilter] = useState("")
  const [selected, setSelected] = useState<Candidate | null>(null)
  const [applying, setApplying] = useState(false)
  const visible = useMemo(() => {
    const text = filter.trim().toLocaleLowerCase()
    if (!text) return candidates ?? []
    return (candidates ?? []).filter((candidate) =>
      `${candidate.title} ${candidate.channel}`.toLocaleLowerCase().includes(text),
    )
  }, [candidates, filter])

  useEffect(() => {
    if (!open) return undefined
    const controller = new AbortController()
    async function load() {
      try {
        const result = await api<Candidate[]>(`/job/matches/${track.occurrence}`, {
          signal: controller.signal,
        })
        if (controller.signal.aborted) return
        setCandidates(result)
      } catch (err) {
        if (controller.signal.aborted) return
        setError(err instanceof Error ? err.message : "YouTube lookup failed. Try again later.")
      }
    }
    void load()
    return () => controller.abort()
  }, [open, track.occurrence])

  async function apply() {
    if (!selected || applying) return
    setApplying(true)
    try {
      await api(`/job/matches/${track.occurrence}`, {
        method: "POST",
        headers: { "X-CSRF-Token": session.csrf ?? "" },
        body: JSON.stringify({ video_id: selected.video_id }),
      })
      // The playlist page resolves this toast when polling sees the rematch finish.
      toast.add({
        id: `rematch-${track.occurrence}`,
        title: "Re-analyzing this song",
        description: `${track.name} · Using the recording you picked.`,
        type: "loading",
        priority: "low",
        timeout: 0,
      })
      onOpenChange(false)
      onApplied(track.occurrence)
    } catch (err) {
      const message = err instanceof Error ? err.message : "Please try again."
      toast.add({
        title: "Couldn't update the recording",
        description: message,
        type: "error",
        priority: "high",
        timeout: 8000,
      })
    } finally {
      setApplying(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Check recording</DialogTitle>
          <DialogDescription>
            {track.name} · {track.artist}. Pick the recording that sounds right, then apply it.
          </DialogDescription>
        </DialogHeader>
        <InputGroup>
          <InputGroupAddon align="inline-start">
            <Search aria-hidden="true" />
          </InputGroupAddon>
          <InputGroupInput
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Filter recordings"
            aria-label="Filter recordings"
            disabled={!candidates}
          />
        </InputGroup>
        <div className="min-w-0">
          <ScrollArea
            className="max-h-72"
            viewportProps={{ className: "h-fit max-h-72" }}
            aria-label="Recording results"
          >
            {error ? (
              <p
                role="alert"
                className="flex items-start gap-2 py-6 pr-3 text-sm text-muted-foreground"
              >
                <CircleAlert
                  className="mt-0.5 size-4 shrink-0 text-destructive"
                  aria-hidden="true"
                />
                {error}
              </p>
            ) : candidates === null ? (
              <div className="flex items-center justify-center gap-2 py-10 pr-3 text-sm text-muted-foreground">
                <Spinner className="size-4" />
                Searching YouTube...
              </div>
            ) : visible.length === 0 ? (
              <Empty>
                <EmptyHeader>
                  <EmptyMedia variant="icon">
                    <Search aria-hidden="true" />
                  </EmptyMedia>
                  <EmptyTitle>No recordings found</EmptyTitle>
                  <EmptyDescription>Try different words to filter the results.</EmptyDescription>
                </EmptyHeader>
              </Empty>
            ) : (
              <ul className="divide-y pr-3">
                {visible.map((candidate) => {
                  const active = selected?.video_id === candidate.video_id
                  return (
                    <li
                      key={candidate.video_id}
                      className="flex flex-wrap items-center gap-2 py-2.5"
                    >
                      <button
                        type="button"
                        onClick={() => setSelected(candidate)}
                        aria-pressed={active}
                        className={cn(
                          "flex min-w-0 flex-1 basis-56 items-center gap-3 rounded-lg p-2 text-left transition-colors duration-150 ease-out outline-none focus-visible:ring-3 focus-visible:ring-ring/30",
                          active ? "bg-muted/60" : "hover:bg-muted/40",
                        )}
                      >
                        <span
                          aria-hidden="true"
                          className={cn(
                            "flex size-8 shrink-0 items-center justify-center rounded-full transition-colors duration-150 ease-out",
                            active
                              ? "bg-foreground text-background"
                              : "bg-muted text-muted-foreground",
                          )}
                        >
                          {active ? (
                            <Play className="size-3.5" />
                          ) : (
                            <span className="size-2 rounded-full bg-current" />
                          )}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium">
                            {candidate.title}
                          </span>
                          <span className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
                            <span className="truncate">{candidate.channel || "YouTube"}</span>
                            {candidate.suggested && <Badge variant="secondary">Matched</Badge>}
                            {candidate.live && <Badge variant="outline">Live</Badge>}
                          </span>
                        </span>
                      </button>
                      {candidate.duration_seconds != null && (
                        <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                          {elapsedTime(candidate.duration_seconds * 1000)}
                        </span>
                      )}
                      <Tooltip>
                        <TooltipTrigger
                          render={
                            <a
                              className={buttonVariants({ variant: "outline", size: "icon-sm" })}
                              aria-label="Open recording on YouTube"
                              href={`https://www.youtube.com/watch?v=${candidate.video_id}`}
                              target="_blank"
                              rel="noreferrer"
                            />
                          }
                        >
                          <ExternalLink aria-hidden="true" />
                        </TooltipTrigger>
                        <TooltipContent>Open on YouTube</TooltipContent>
                      </Tooltip>
                    </li>
                  )
                })}
              </ul>
            )}
          </ScrollArea>
        </div>
        <DialogFooter>
          <DialogClose render={<Button variant="outline" disabled={applying} />}>
            Cancel
          </DialogClose>
          <Button
            onClick={() => void apply()}
            disabled={!selected || applying || !!error || candidates?.length === 0}
          >
            {applying ? <Spinner data-icon="inline-start" /> : null}
            Use this recording
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
