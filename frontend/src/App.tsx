import { useState } from "react"
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
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { api, ApiError, type Job, type Playlist, type Session } from "@/lib/api"

function Loading() {
  return (
    <p aria-live="polite" className="flex items-center gap-2 py-10 text-sm text-muted-foreground">
      <LoaderCircle className="size-4 motion-safe:animate-spin" aria-hidden="true" />
      Loading...
    </p>
  )
}

function Shell() {
  const session = useLoaderData<Session>()
  const navigation = useNavigation()
  const [error, setError] = useState("")
  const [leaving, setLeaving] = useState(false)
  async function logout() {
    setLeaving(true)
    try {
      await api("/auth/logout", { method: "POST", headers: { "X-CSRF-Token": session.csrf ?? "" } })
      window.location.assign("/")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Please try again.")
      setLeaving(false)
    }
  }
  return (
    <div className="min-h-dvh">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-background focus:p-3"
      >
        Skip to content
      </a>
      <header className="border-b">
        <div className="mx-auto flex h-18 max-w-5xl items-center justify-between gap-4 px-5 sm:px-8">
          <Link
            to={session.user ? "/playlists" : "/"}
            className="flex items-center gap-2.5 rounded-md font-semibold tracking-tight"
          >
            <ListMusic className="size-5" aria-hidden="true" />
            Playlist sorter
          </Link>
          {session.user && (
            <Button variant="ghost" size="sm" onClick={() => void logout()} disabled={leaving}>
              <LogOut aria-hidden="true" />
              Sign out
            </Button>
          )}
        </div>
      </header>
      <main
        id="main"
        tabIndex={-1}
        className="mx-auto max-w-5xl px-5 py-10 outline-none sm:px-8 sm:py-14"
        aria-busy={navigation.state === "loading"}
      >
        {error && (
          <Alert variant="destructive" className="mb-6">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        {navigation.state === "loading" && (
          <div aria-live="polite" className="mb-4 text-sm text-muted-foreground">
            Loading...
          </div>
        )}
        <Outlet />
      </main>
    </div>
  )
}

function Welcome() {
  const session = useRouteLoaderData<Session>("root")
  const [params] = useSearchParams()
  if (session?.user) return <Navigate to="/playlists" replace />
  return (
    <section className="mx-auto max-w-xl py-8 sm:py-16">
      <div className="mb-8 flex size-14 items-center justify-center rounded-2xl bg-muted">
        <Music2 className="size-7" aria-hidden="true" />
      </div>
      <h1 className="text-4xl leading-[1.12] font-semibold tracking-tight sm:text-5xl">
        Put your songs
        <br />
        in a smoother order.
      </h1>
      <p className="mt-5 max-w-sm text-base leading-7 text-muted-foreground">
        Pick the first song. We'll find a smooth order for the rest.
      </p>
      {params.has("error") && (
        <Alert variant="destructive" className="mt-6">
          <AlertDescription>We couldn't connect Spotify. Please try again.</AlertDescription>
        </Alert>
      )}
      {session?.configured ? (
        <Button
          size="lg"
          className="mt-8"
          render={<a aria-label="Connect Spotify" href="/api/auth/login" />}
        >
          Connect Spotify
          <ArrowRight aria-hidden="true" />
        </Button>
      ) : (
        <Alert className="mt-8">
          <AlertDescription>Spotify isn't set up yet. Please try again later.</AlertDescription>
        </Alert>
      )}
      <p className="mt-4 text-sm text-muted-foreground">You can check the order before saving.</p>
    </section>
  )
}

function PlaylistList() {
  const playlists = useRouteLoaderData<Playlist[]>("playlists") ?? []
  const revalidator = useRevalidator()
  const [search, setSearch] = useState("")
  const filtered = playlists.filter((playlist) =>
    playlist.name.toLocaleLowerCase().includes(search.toLocaleLowerCase().trim()),
  )
  return (
    <section className="mx-auto max-w-2xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Your playlists</h1>
          <p className="mt-2 text-muted-foreground">Choose a playlist you want to sort.</p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Refresh playlists"
          onClick={() => void revalidator.revalidate()}
          disabled={revalidator.state !== "idle"}
        >
          <RefreshCw
            className={revalidator.state !== "idle" ? "motion-safe:animate-spin" : ""}
            aria-hidden="true"
          />
        </Button>
      </div>
      {playlists.length > 0 ? (
        <>
          <label htmlFor="playlist-search" className="mt-8 mb-2 block text-sm font-medium">
            Find a playlist
          </label>
          <div className="relative">
            <Search
              className="pointer-events-none absolute top-3 left-3 size-4 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              id="playlist-search"
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search by name"
              className="h-10 pl-10"
            />
          </div>
          <ul className="mt-5 divide-y">
            {filtered.map((playlist) => (
              <li key={playlist.id}>
                <Link
                  to={`/playlists/${playlist.id}`}
                  className="group flex items-center gap-4 rounded-lg py-4 pr-2 transition-colors hover:bg-muted/50"
                >
                  {playlist.image ? (
                    <img
                      src={playlist.image}
                      alt=""
                      loading="lazy"
                      width={64}
                      height={64}
                      className="size-16 shrink-0 rounded-lg object-cover"
                    />
                  ) : (
                    <div className="flex size-16 shrink-0 items-center justify-center rounded-lg bg-muted">
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
      <p className="mt-6 text-xs leading-5 text-muted-foreground">
        Only playlists you can edit are shown.
      </p>
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
        <Button variant="outline" render={<a aria-label="Go back" href="/" />}>
          Go back
        </Button>
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
