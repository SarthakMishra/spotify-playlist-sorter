import { useEffect, useRef, useState } from "react"
import { Link } from "react-router"
import { ChevronRight, ListMusic, LoaderCircle } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { Progress, ProgressLabel, ProgressValue } from "@/components/ui/progress"
import { getQueue, type QueueEntry } from "@/lib/api"

function etaLabel(seconds: number | null): string {
  if (seconds == null) return ""
  if (seconds < 90) return "About a minute left"
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `About ${minutes} min left`
  return `About ${Math.round(minutes / 10) * 10} min left`
}

function QueueRow({ entry }: { entry: QueueEntry }) {
  const running = entry.status === "running"
  return (
    <li>
      <Link
        to={`/playlists/${entry.playlist_id}`}
        className="group block rounded-xl border bg-card transition-colors duration-150 ease-out outline-none hover:bg-muted/40 focus-visible:ring-3 focus-visible:ring-ring/30"
      >
        <div className="flex items-center gap-3 p-4">
          {running ? (
            <Badge>
              <LoaderCircle className="motion-safe:animate-spin" aria-hidden="true" />
              Analyzing
            </Badge>
          ) : (
            <Badge variant="secondary">Waiting · #{entry.queue_position}</Badge>
          )}
          <p className="min-w-0 flex-1 truncate font-medium">{entry.name}</p>
          <span aria-live="polite" className="shrink-0 text-xs text-muted-foreground tabular-nums">
            {running
              ? etaLabel(entry.eta_seconds) ||
                (entry.total ? `${entry.completed} of ${entry.total} analyzed` : "")
              : "Waiting for its turn"}
          </span>
          <ChevronRight
            className="size-4 shrink-0 text-muted-foreground transition-transform duration-150 ease-out group-hover:translate-x-0.5 motion-reduce:transition-none"
            aria-hidden="true"
          />
        </div>
        {running && entry.total > 0 && (
          <div className="px-4 pb-4">
            <Progress value={entry.completed} max={entry.total}>
              <ProgressLabel className="sr-only">Analyzing {entry.name}</ProgressLabel>
              <ProgressValue className="sr-only">
                {() => `${entry.completed} of ${entry.total}`}
              </ProgressValue>
            </Progress>
          </div>
        )}
      </Link>
    </li>
  )
}

// Poll the shared queue every second while lines remain, then settle.
export function QueueRoute() {
  const [entries, setEntries] = useState<QueueEntry[] | null>(null)
  const [error, setError] = useState("")
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    async function poll() {
      try {
        const next = await getQueue({ signal: controller.signal })
        if (controller.signal.aborted) return
        setEntries(next)
        timer.current = setTimeout(poll, 1000)
      } catch (err) {
        if (controller.signal.aborted) return
        setError(
          err instanceof Error ? err.message : "We couldn't load the queue. Please try again.",
        )
        setEntries([])
      }
    }
    void poll()
    return () => {
      controller.abort()
      if (timer.current) clearTimeout(timer.current)
    }
  }, [])

  return (
    <section className="mx-auto max-w-2xl">
      <h1 className="text-3xl font-semibold tracking-tight">Analysis queue</h1>
      <p className="mt-2 text-muted-foreground">
        Playlists are analyzed one at a time. Your chosen recordings always go first.
      </p>
      {error ? (
        <p role="alert" className="mt-8 text-sm text-destructive">
          {error}
        </p>
      ) : entries === null ? (
        <p
          aria-live="polite"
          className="mt-10 flex items-center gap-2 text-sm text-muted-foreground"
        >
          <LoaderCircle className="size-4 motion-safe:animate-spin" aria-hidden="true" />
          Loading...
        </p>
      ) : entries.length === 0 ? (
        <Empty className="mt-10">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <ListMusic aria-hidden="true" />
            </EmptyMedia>
            <EmptyTitle>The queue is clear</EmptyTitle>
            <EmptyDescription>
              Nothing is being analyzed right now. Pick a playlist to arrange it.
            </EmptyDescription>
          </EmptyHeader>
          <Button variant="outline" render={<Link to="/playlists" />}>
            Choose a playlist
          </Button>
        </Empty>
      ) : (
        <ul className="mt-6 space-y-2">
          {entries.map((entry) => (
            <QueueRow key={entry.playlist_id} entry={entry} />
          ))}
        </ul>
      )}
    </section>
  )
}
