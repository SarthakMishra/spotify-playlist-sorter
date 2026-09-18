import { useDeferredValue, useEffect, useState } from "react"
import {
  Link,
  Navigate,
  Outlet,
  createBrowserRouter,
  redirectDocument,
  useLoaderData,
  useNavigation,
  useRevalidator,
  useRouteError,
  useRouteLoaderData,
  useSearchParams,
  type LoaderFunctionArgs,
} from "react-router"
import {
  ArrowRight,
  ChevronRight,
  ListMusic,
  LoaderCircle,
  LogOut,
  Music2,
  RefreshCw,
  Search,
  Settings,
} from "lucide-react"
import { Button, buttonVariants } from "@/components/ui/button"
import { ModeToggle } from "@/components/mode-toggle"
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { toast } from "@/components/ui/toast"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { api, ApiError, type Job, type Playlist, type Session, type YouTubeAccess } from "@/lib/api"

// Warm the lazy route chunks on hover/focus so navigation feels instant.
const preloadPlaylistPage = () => {
  void import("@/components/playlist-page")
}
const preloadYouTubeAccess = () => {
  void import("@/components/youtube-access")
}

function Loading({ className = "min-h-dvh" }: { className?: string }) {
  return (
    <p
      aria-live="polite"
      className={`flex items-center justify-center gap-2 text-sm text-muted-foreground ${className}`}
    >
      <LoaderCircle
        className="size-4 motion-safe:animate-spin"
        strokeWidth={1.5}
        aria-hidden="true"
      />
      Loading...
    </p>
  )
}

function Shell() {
  const session = useLoaderData<Session>()
  const navigation = useNavigation()
  const [leaving, setLeaving] = useState(false)
  async function logout() {
    setLeaving(true)
    try {
      await api("/auth/logout", { method: "POST", headers: { "X-CSRF-Token": session.csrf ?? "" } })
      window.location.assign("/")
    } catch (err) {
      toast.add({
        title: "Couldn't sign out",
        description: err instanceof Error ? err.message : "Please try again.",
        type: "error",
        priority: "high",
        timeout: 8000,
      })
      setLeaving(false)
    }
  }
  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-background focus:p-3"
      >
        Skip to content
      </a>
      <header className="relative px-5 after:absolute after:inset-x-0 after:bottom-0 after:h-px after:bg-linear-to-r after:from-background after:via-border after:to-background sm:px-8">
        <div className="mx-auto flex min-h-12 max-w-2xl flex-wrap items-center justify-between gap-3 py-3">
          <Link
            to={session.user ? "/playlists" : "/"}
            className="flex items-center gap-2 rounded-md text-sm font-semibold tracking-tight"
          >
            <ListMusic className="size-5" aria-hidden="true" />
            Playlist sorter
          </Link>
          <div className="flex items-center gap-1 max-sm:w-full max-sm:justify-end">
            {session.user && (
              <Tooltip>
                <TooltipTrigger
                  render={
                    <Link
                      to="/youtube"
                      onMouseEnter={preloadYouTubeAccess}
                      onFocus={preloadYouTubeAccess}
                      className={buttonVariants({ variant: "ghost", size: "icon-sm" })}
                      aria-label="Settings"
                    />
                  }
                >
                  <Settings aria-hidden="true" />
                </TooltipTrigger>
                <TooltipContent>Settings</TooltipContent>
              </Tooltip>
            )}
            <ModeToggle />
            {session.user && (
              <Tooltip>
                <TooltipTrigger
                  render={
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label="Sign out"
                      onClick={() => void logout()}
                      disabled={leaving}
                    />
                  }
                >
                  <LogOut aria-hidden="true" />
                </TooltipTrigger>
                <TooltipContent>Sign out</TooltipContent>
              </Tooltip>
            )}
          </div>
        </div>
      </header>
      <main
        id="main"
        tabIndex={-1}
        className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-5 py-6 outline-none sm:px-8 sm:py-8"
        aria-busy={navigation.state === "loading"}
      >
        {navigation.state === "loading" && <Loading className="flex-1" />}
        <div hidden={navigation.state === "loading"}>
          <Outlet />
        </div>
      </main>
    </div>
  )
}

function Welcome() {
  const session = useRouteLoaderData<Session>("root")
  const [params, setParams] = useSearchParams()
  useEffect(() => {
    if (!params.has("error")) return
    toast.add({
      id: "spotify-login-error",
      title: "Couldn't connect Spotify",
      description: "Please try again.",
      type: "error",
      priority: "high",
      timeout: 8000,
    })
    setParams(
      (current) => {
        current.delete("error")
        return current
      },
      { replace: true },
    )
  }, [params, setParams])
  if (session?.user) return <Navigate to="/playlists" replace />
  return (
    <section className="mx-auto max-w-2xl py-8 sm:py-16">
      <div className="mb-8 flex size-14 items-center justify-center rounded-2xl bg-muted">
        <Music2 className="size-7" aria-hidden="true" />
      </div>
      <h1 className="text-4xl leading-heading font-semibold tracking-tight sm:text-5xl">
        Put your songs
        <br />
        in a smoother order.
      </h1>
      <p className="mt-5 max-w-sm text-base leading-7 text-muted-foreground">
        Pick a playlist. Choose a smooth flow or more variety, then review the order before saving.
      </p>
      {session?.configured ? (
        <a
          className={buttonVariants({ size: "lg", className: "mt-8" })}
          aria-label="Connect Spotify"
          href="/api/auth/login"
        >
          Connect Spotify
          <ArrowRight aria-hidden="true" />
        </a>
      ) : (
        <Alert className="mt-8">
          <AlertDescription>Spotify isn't set up yet. Please try again later.</AlertDescription>
        </Alert>
      )}
      <p className="mt-4 text-sm text-muted-foreground">You can analyze the order before saving.</p>
    </section>
  )
}

function PlaylistList() {
  const playlists = useRouteLoaderData<Playlist[]>("playlists") ?? []
  const revalidator = useRevalidator()
  const [search, setSearch] = useState("")
  const deferredSearch = useDeferredValue(search)
  const query = deferredSearch.toLocaleLowerCase().trim()
  const filtered = playlists.filter((playlist) => playlist.name.toLocaleLowerCase().includes(query))
  return (
    <section className="mx-auto max-w-2xl">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-3xl font-semibold tracking-tight">Your playlists</h1>
        <Button
          variant="outline"
          size="sm"
          onClick={() => void revalidator.revalidate()}
          disabled={revalidator.state !== "idle"}
        >
          <RefreshCw
            className={revalidator.state !== "idle" ? "motion-safe:animate-spin" : ""}
            aria-hidden="true"
          />
          Refresh
        </Button>
      </div>
      <p className="mt-2 text-muted-foreground">Choose a playlist you want to sort.</p>
      {playlists.length > 0 ? (
        <>
          <InputGroup className="mt-8">
            <InputGroupAddon align="inline-start">
              <Search aria-hidden="true" />
            </InputGroupAddon>
            <InputGroupInput
              id="playlist-search"
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              aria-label="Search your playlists"
              placeholder="Search your playlists"
            />
          </InputGroup>
          <ul className="mt-5 divide-y">
            {filtered.map((playlist) => (
              <li key={playlist.id} className="py-2">
                <Link
                  to={`/playlists/${playlist.id}`}
                  onMouseEnter={preloadPlaylistPage}
                  onFocus={preloadPlaylistPage}
                  className="group flex items-center gap-4 rounded-2xl p-3 transition-colors hover:bg-muted/50"
                >
                  {playlist.image ? (
                    <img
                      src={playlist.image}
                      alt=""
                      loading="lazy"
                      width={64}
                      height={64}
                      className="size-16 shrink-0 rounded-sm object-cover outline outline-black/10 dark:outline-white/10"
                    />
                  ) : (
                    <div className="flex size-16 shrink-0 items-center justify-center rounded-sm bg-muted">
                      <Music2 className="size-6 text-muted-foreground" aria-hidden="true" />
                    </div>
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{playlist.name}</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {playlist.total} {playlist.total === 1 ? "song" : "songs"}
                    </p>
                  </div>
                  <ChevronRight
                    className="size-5 shrink-0 text-muted-foreground"
                    aria-hidden="true"
                  />
                </Link>
              </li>
            ))}
          </ul>
          {!filtered.length && (
            <p aria-live="polite" className="py-12 text-center text-muted-foreground">
              No playlists match that name.
            </p>
          )}
        </>
      ) : (
        <div className="py-14">
          <ListMusic className="mb-4 size-8 text-muted-foreground" aria-hidden="true" />
          <h2 className="font-medium">No playlists yet</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Create a playlist on Spotify, then refresh this page.
          </p>
        </div>
      )}
    </section>
  )
}

function RouteError() {
  const error = useRouteError()
  return (
    <main className="mx-auto max-w-lg px-6 py-20">
      <h1 className="text-2xl font-semibold">We couldn't load this page.</h1>
      <p role="alert" className="mt-3 text-muted-foreground">
        {error instanceof Error ? error.message : "Please try again."}
      </p>
      <div className="mt-6 flex gap-3">
        <Button onClick={() => window.location.reload()}>Try again</Button>
        <a className={buttonVariants({ variant: "outline" })} aria-label="Go back" href="/">
          Go back
        </a>
      </div>
    </main>
  )
}

async function playlistLoader({ request }: LoaderFunctionArgs) {
  try {
    return await api<Playlist[]>("/playlists", { signal: request.signal })
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) throw redirectDocument("/")
    throw error
  }
}

export const router = createBrowserRouter([
  {
    id: "root",
    path: "/",
    loader: ({ request }) => api<Session>("/session", { signal: request.signal }),
    Component: Shell,
    ErrorBoundary: RouteError,
    HydrateFallback: Loading,
    children: [
      { index: true, Component: Welcome },
      {
        id: "playlists",
        path: "playlists",
        loader: playlistLoader,
        children: [
          { index: true, Component: PlaylistList },
          {
            path: ":playlistId",
            loader: ({ request }) => api<Job | null>("/job", { signal: request.signal }),
            lazy: async () => ({
              Component: (await import("@/components/playlist-page")).PlaylistRoute,
            }),
          },
        ],
      },
      {
        path: "youtube",
        loader: async ({ request }) => {
          try {
            return await api<YouTubeAccess>("/youtube", { signal: request.signal })
          } catch (error) {
            if (error instanceof ApiError && error.status === 401) throw redirectDocument("/")
            throw error
          }
        },
        lazy: async () => ({
          Component: (await import("@/components/youtube-access")).YouTubeAccessPage,
        }),
      },
      {
        path: "*",
        element: (
          <section>
            <h1 className="text-2xl font-semibold">This page wasn't found.</h1>
            <Link to="/" className="mt-4 inline-block underline">
              Go back
            </Link>
          </section>
        ),
      },
    ],
  },
])
