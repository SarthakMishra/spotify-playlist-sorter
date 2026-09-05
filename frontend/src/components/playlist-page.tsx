import { lazy, Suspense, useEffect, useRef, useState } from "react"
import { Link, useLoaderData, useParams, useRouteLoaderData } from "react-router"
import { ArrowLeft, ArrowRight, Check, ExternalLink, LoaderCircle, Music2 } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
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

function SongList({ tracks, label }: { tracks: Track[]; label: string }) {
  return (
    <Table className="table-fixed">
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
            <TableCell className="align-top text-muted-foreground tabular-nums">
              {index + 1}
            </TableCell>
            <TableCell className="whitespace-normal">
              <p className="font-medium break-words">{track.name}</p>
              <p className="mt-1 break-words text-muted-foreground">{track.artist}</p>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function PlaylistPage({ playlist, initialJob }: { playlist: Playlist; initialJob: Job | null }) {
  const session = useRouteLoaderData<Session>("root")
  const [job, setJob] = useState(initialJob?.playlist_id === playlist.id ? initialJob : null)
  const [error, setError] = useState("")
  const [pending, setPending] = useState(false)
  const [firstTrackId, setFirstTrackId] = useState("")
  const [detailsOpen, setDetailsOpen] = useState(false)
  const actionController = useRef<AbortController | null>(null)
  const jobStatus = job?.status
  const busy = pending || isWorking(job)
  const otherJob =
    initialJob?.playlist_id !== playlist.id && isWorking(initialJob) ? initialJob : null
  const tracks = job?.tracks ?? []
  const firstId = firstTrackId || job?.sorted_tracks[0]?.id || tracks[0]?.id || ""
  const choices = [...new Map(tracks.map((track) => [track.id, track])).values()]
  const firstSong = choices.find((track) => track.id === firstId) ?? null
  const hasPreview = !!job?.sorted_tracks.length
  const firstChanged = hasPreview && firstId !== job?.sorted_tracks[0]?.id

  useEffect(() => () => actionController.current?.abort(), [])

  useEffect(() => {
    if (error || !jobStatus || !["analyzing", "sorting", "saving"].includes(jobStatus))
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
        setError(
          err instanceof Error ? err.message : "We couldn't check progress. Please try again.",
        )
      }
    }
    timer = setTimeout(poll, 700)
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
    // Status controls the polling lifetime. Each request schedules the next one after it finishes.
  }, [jobStatus, playlist.id, error])

  async function run(action: "analyze" | "sort" | "save") {
    if (busy) return
    const controller = new AbortController()
    actionController.current = controller
    setPending(true)
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
                ...(action === "sort" ? { first_track_id: firstId } : {}),
              }),
      })
      if (controller.signal.aborted) return
      if (action === "analyze") setFirstTrackId("")
      setJob(next)
    } catch (err) {
      if (controller.signal.aborted) return
      if (err instanceof ApiError && err.status === 401) {
        window.location.assign("/")
        return
      }
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.")
    } finally {
      if (!controller.signal.aborted) setPending(false)
    }
  }

  return (
    <section className="mx-auto max-w-2xl">
      <Link
        to="/playlists"
        className="mb-7 inline-flex items-center gap-2 rounded-md text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        Your playlists
      </Link>
      <div className="flex items-center gap-5">
        {playlist.image ? (
          <img
            src={playlist.image}
            alt=""
            width={88}
            height={88}
            className="size-20 shrink-0 rounded-xl object-cover sm:size-22"
          />
        ) : (
          <div className="flex size-20 shrink-0 items-center justify-center rounded-xl bg-muted">
            <Music2 className="size-8 text-muted-foreground" aria-hidden="true" />
          </div>
        )}
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight break-words sm:text-3xl">
            {playlist.name}
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {playlist.total} {playlist.total === 1 ? "song" : "songs"}
          </p>
        </div>
      </div>

      {(error || job?.error) && (
        <Alert variant="destructive" className="mt-7">
          <AlertDescription>
            {error || job?.error}
            {isWorking(job) && error && (
              <Button
                className="mt-2 w-fit"
                size="sm"
                variant="outline"
                onClick={() => {
                  setError("")
                }}
              >
                Check progress
              </Button>
            )}
          </AlertDescription>
        </Alert>
      )}

      {otherJob && !job ? (
        <Alert className="mt-8">
          <AlertDescription>
            Another playlist is still being checked.
            <Link to={`/playlists/${otherJob.playlist_id}`} className="underline">
              See progress
            </Link>
          </AlertDescription>
        </Alert>
      ) : (
        (!job || job.status === "error") && (
          <div className="mt-9">
            <h2 className="font-medium">Let's check the songs first.</h2>
            <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">
              This can take a few minutes. Your playlist stays as it is until you save.
            </p>
            <Button
              className="mt-5"
              onClick={() => void run("analyze")}
              disabled={busy || playlist.total === 0}
            >
              {pending && <LoaderCircle className="motion-safe:animate-spin" aria-hidden="true" />}
              {job ? "Check again" : "Check songs"}
              <ArrowRight aria-hidden="true" />
            </Button>
            {playlist.total === 0 && (
              <p className="mt-3 text-sm text-muted-foreground">Add some songs on Spotify first.</p>
            )}
          </div>
        )
      )}

      {job && isWorking(job) && (
        <div className="my-9 rounded-xl border p-5" aria-live="polite">
          {job.status === "analyzing" ? (
            <>
              <Progress value={job.total ? job.completed : null} max={job.total || 100}>
                <ProgressLabel>Checking songs...</ProgressLabel>
                <ProgressValue>
                  {() => (job.total ? `${job.completed} of ${job.total}` : "Getting ready")}
                </ProgressValue>
              </Progress>
              <p className="mt-3 text-sm text-muted-foreground">
                You can leave this page and come back.
              </p>
            </>
          ) : (
            <p className="flex items-center gap-2 text-sm">
              <LoaderCircle className="size-4 motion-safe:animate-spin" aria-hidden="true" />
              {job.status === "sorting" ? "Finding a smooth order..." : "Saving to Spotify..."}
            </p>
          )}
        </div>
      )}

      {!!tracks.length && job && job.status !== "error" && (
        <>
          <div className="mt-9 border-t pt-7">
            <label htmlFor="first-song" className="mb-2 block text-sm font-medium">
              First song
            </label>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
              <div className="min-w-0 flex-1">
                <Combobox
                  items={choices}
                  value={firstSong}
                  onValueChange={(track) => setFirstTrackId(track?.id ?? "")}
                  itemToStringLabel={(track) => `${track.name} · ${track.artist}`}
                  itemToStringValue={(track) => track.id}
                  isItemEqualToValue={(a, b) => a.id === b.id}
                  disabled={busy}
                >
                  <ComboboxInput id="first-song" className="w-full" placeholder="Find a song" />
                  <ComboboxContent>
                    <ComboboxEmpty>No songs found.</ComboboxEmpty>
                    <ComboboxList>
                      {(track: Track) => (
                        <ComboboxItem key={track.id} value={track}>
                          <div className="min-w-0">
                            <p className="truncate">{track.name}</p>
                            <p className="truncate text-xs text-muted-foreground">{track.artist}</p>
                          </div>
                        </ComboboxItem>
                      )}
                    </ComboboxList>
                  </ComboboxContent>
                </Combobox>
              </div>
              <Button onClick={() => void run("sort")} disabled={busy || !firstId}>
                {hasPreview ? "Sort again" : "Sort playlist"}
                <ArrowRight aria-hidden="true" />
              </Button>
            </div>
            <p className="mt-2 text-xs leading-5 text-muted-foreground">
              We'll start here and order the rest for you.
            </p>
          </div>
          {job.kept_count > 0 && (
            <Alert className="mt-6">
              <AlertDescription>
                {job.kept_count}{" "}
                {job.kept_count === 1
                  ? "song couldn't be checked. It will stay"
                  : "songs couldn't be checked. They will stay"}{" "}
                in the same {job.kept_count === 1 ? "place" : "places"}.
              </AlertDescription>
            </Alert>
          )}
          <div className="mt-8">
            {hasPreview ? (
              <Tabs defaultValue="new" key={job.sorted_tracks.map((track) => track.id).join("")}>
                <TabsList aria-label="Song order">
                  <TabsTrigger value="new">New order</TabsTrigger>
                  <TabsTrigger value="original">Original</TabsTrigger>
                </TabsList>
                <TabsContent value="new">
                  <SongList tracks={job.sorted_tracks} label="New song order" />
                </TabsContent>
                <TabsContent value="original">
                  <SongList tracks={tracks} label="Original song order" />
                </TabsContent>
              </Tabs>
            ) : (
              <SongList tracks={tracks} label="Songs in your playlist" />
            )}
          </div>
          {hasPreview && (
            <>
              <details
                className="mt-6 border-t py-5"
                onToggle={(event) => setDetailsOpen(event.currentTarget.open)}
              >
                <summary className="w-fit cursor-pointer rounded-md text-sm font-medium">
                  Song details
                </summary>
                {detailsOpen && (
                  <Suspense
                    fallback={
                      <p className="py-5 text-sm text-muted-foreground">Loading details...</p>
                    }
                  >
                    <SongDetails tracks={job.sorted_tracks} transitions={job.transitions} />
                  </Suspense>
                )}
              </details>
              <div className="mt-3 flex flex-col items-start gap-4 border-t py-6 sm:flex-row sm:items-center sm:justify-between">
                <div aria-live="polite">
                  {job.status === "saved" ? (
                    <p className="flex items-center gap-2 text-sm font-medium">
                      <Check className="size-4" aria-hidden="true" />
                      Saved to Spotify.
                    </p>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      {firstChanged
                        ? "Sort again to use this first song."
                        : "Ready? Save this order to your playlist."}
                    </p>
                  )}
                </div>
                {job.status === "saved" ? (
                  <Button
                    variant="outline"
                    render={
                      <a
                        aria-label="Open Spotify"
                        href={`https://open.spotify.com/playlist/${playlist.id}`}
                        target="_blank"
                        rel="noreferrer"
                      />
                    }
                  >
                    Open Spotify
                    <ExternalLink aria-hidden="true" />
                  </Button>
                ) : (
                  <Button onClick={() => void run("save")} disabled={busy || firstChanged}>
                    Save to Spotify
                  </Button>
                )}
              </div>
            </>
          )}
        </>
      )}
    </section>
  )
}
