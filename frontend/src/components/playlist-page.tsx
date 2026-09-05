import { lazy, Suspense, useEffect, useEffectEvent, useRef, useState } from "react"
import { Link, useLoaderData, useParams, useRouteLoaderData } from "react-router"
import { ArrowLeft, ArrowRight, ExternalLink, LoaderCircle, Music2 } from "lucide-react"
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
              <p className="font-medium break-words">{track.name}</p>
              <p className="mt-0.5 break-words text-muted-foreground">{track.artist}</p>
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
  const [pending, setPending] = useState<"analyze" | "sort" | "save" | null>(null)
  const [firstTrackId, setFirstTrackId] = useState("")
  const actionController = useRef<AbortController | null>(null)
  const progressToast = useRef<string | null>(null)
  const jobStatus = job?.status
  const busy = pending !== null || isWorking(job)
  const activity = pending === "sort" ? "sorting" : pending === "save" ? "saving" : jobStatus
  const otherJob =
    initialJob?.playlist_id !== playlist.id && isWorking(initialJob) ? initialJob : null
  const checking =
    pending === "analyze" ||
    jobStatus === "analyzing" ||
    (!job && !otherJob && playlist.total > 0 && !error)
  const tracks = job?.tracks ?? []
  const firstId = firstTrackId || job?.sorted_tracks[0]?.id || tracks[0]?.id || ""
  const choices = [...new Map(tracks.map((track) => [track.id, track])).values()]
  const firstSong = choices.find((track) => track.id === firstId) ?? null
  const hasPreview = !!job?.sorted_tracks.length
  const firstChanged = hasPreview && firstId !== job?.sorted_tracks[0]?.id

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
    if (error) {
      if (progressToast.current) toast.close(progressToast.current)
      progressToast.current = null
    } else if (activity === "sorting" || activity === "saving") {
      progressToast.current = toast.add({
        id: `playlist-${playlist.id}`,
        title: activity === "sorting" ? "Finding a smooth order..." : "Saving to Spotify...",
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
            : "Your new order is ready",
        description: job?.error || playlist.name,
        type: failed ? "error" : "success",
        priority: failed ? "high" : "low",
        timeout: failed ? 8000 : 5000,
      })
      progressToast.current = null
    }
  }, [activity, error, job?.error, playlist.id, playlist.name])

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
      const message = err instanceof Error ? err.message : "Please try again."
      if (action === "analyze") {
        setError(message)
      } else {
        toast.add({
          id: progressToast.current ?? undefined,
          title: "Couldn't start the request",
          description: message,
          type: "error",
          priority: "high",
          timeout: 8000,
        })
      }
      progressToast.current = null
    } finally {
      if (!controller.signal.aborted) setPending(null)
    }
  }

  return (
    <section className="mx-auto max-w-2xl">
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
          <h1 className="text-2xl font-semibold tracking-tight break-words sm:text-3xl">
            {playlist.name}
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {playlist.total} {playlist.total === 1 ? "song" : "songs"}
          </p>
        </div>
      </div>

      {pending !== "analyze" && (error || job?.error) && (
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

      {!job && !otherJob && playlist.total === 0 && (
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
        <div className="my-8 rounded-xl border bg-muted/20 p-5 sm:p-6" aria-live="polite">
          <Progress
            className="items-center gap-y-4"
            value={jobStatus === "analyzing" && job?.total ? job.completed : null}
            max={job?.total || 100}
          >
            <h2>
              <ProgressLabel className="flex items-center gap-2 text-base font-semibold">
                <LoaderCircle className="size-4 motion-safe:animate-spin" aria-hidden="true" />
                Checking songs
              </ProgressLabel>
            </h2>
            <ProgressValue className="text-xs">
              {() =>
                jobStatus === "analyzing" && job?.total
                  ? `${job.completed} of ${job.total}`
                  : "Getting ready"
              }
            </ProgressValue>
          </Progress>
          <p className="mt-4 text-sm leading-6 text-muted-foreground">
            You can leave this page and come back. Your playlist stays as it is until you save.
          </p>
        </div>
      )}

      {!!tracks.length && job && job.status !== "error" && (
        <>
          <div className="mt-6 border-t pt-5">
            <label htmlFor="first-song" className="block text-base font-semibold">
              First song
            </label>
            <p className="mt-1 text-sm text-muted-foreground">
              We'll start here and order the rest for you.
            </p>
            <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-start">
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
              <Button
                variant={hasPreview ? "outline" : "default"}
                onClick={() => void run("sort")}
                disabled={busy || !firstId}
              >
                {hasPreview ? "Sort again" : "Sort playlist"}
                <ArrowRight aria-hidden="true" />
              </Button>
            </div>
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
          {hasPreview && (
            <div className="mt-6 flex flex-col gap-3 border-t pt-5 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-base font-semibold">Playlist preview</h2>
                <p aria-live="polite" className="mt-1 text-sm text-muted-foreground">
                  {firstChanged
                    ? "Sort again to use this first song."
                    : "Review the song order below."}
                </p>
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
                  <TabsTrigger value="new">New order</TabsTrigger>
                  <TabsTrigger value="original">Original</TabsTrigger>
                  <TabsTrigger value="details">Song details</TabsTrigger>
                </TabsList>
                <TabsContent value="new">
                  <SongList tracks={job.sorted_tracks} label="New song order" />
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
                    <SongDetails tracks={job.sorted_tracks} transitions={job.transitions} />
                  </Suspense>
                </TabsContent>
              </Tabs>
            ) : (
              <SongList tracks={tracks} label="Songs in your playlist" />
            )}
          </div>
        </>
      )}
    </section>
  )
}
