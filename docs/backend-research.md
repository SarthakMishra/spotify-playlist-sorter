# Backend migration research

Checked 5 September 2026 against the current docs, package releases, and installed Spotipy source.

## Decisions

- FastAPI 0.141.1 has native `app.frontend("/", directory=..., fallback="index.html")`. It gives API routes priority, supports browser navigation to SPA routes, and returns 404 for missing assets. Use it instead of writing a catch-all file server. Explicitly reserve `/api` so unknown API paths never return HTML. [Frontend docs](https://fastapi.tiangolo.com/tutorial/frontend/)
- Keep synchronous Spotipy and analysis calls in synchronous endpoints or background functions. FastAPI runs these in its thread pool. Use lifespan for process-owned session state. [Concurrency](https://fastapi.tiangolo.com/async/), [lifespan](https://fastapi.tiangolo.com/advanced/events/)
- Return an accepted response for analysis and expose progress through a session-owned job. Poll only while work is running. Bound concurrent analysis because each playlist already starts download workers and writes a shared analysis cache. FastAPI background tasks suit this small, single-process app; a durable queue becomes necessary if jobs must survive restarts or run across servers. [Background tasks and caveat](https://fastapi.tiangolo.com/tutorial/background-tasks/)
- Use Pydantic request/response models and validate identifiers before external calls. Keep errors short, with details in backend logs. [Request bodies](https://fastapi.tiangolo.com/tutorial/body/), [response models](https://fastapi.tiangolo.com/tutorial/response-model/)
- Spotify credentials belong in server environment variables. Use Authorization Code flow with a random, single-use state and an expiring HttpOnly session cookie. Store tokens only in the server's session-specific Spotipy `MemoryCacheHandler`. Signed cookie session data is readable, so do not put Spotify tokens there. Require a per-session CSRF header for writes. [Spotify code flow](https://developer.spotify.com/documentation/web-api/tutorials/code-flow), [Spotipy](https://spotipy.readthedocs.io/en/latest/), [Starlette sessions](https://starlette.dev/middleware/#sessionmiddleware)
- Serve browser and API from the same origin in production; proxy `/api` in Vite during development. This avoids a separate CORS configuration. Use the public browser origin in the OAuth callback URL. Spotify requires HTTPS except explicit loopback IPs; `localhost` is not accepted. [Redirect URI rules](https://developer.spotify.com/documentation/web-api/concepts/redirect_uri)
- Build the SPA in a Node Docker stage and copy only its output into the Python runtime. Keep ffmpeg and libsndfile. Run one Uvicorn worker because sessions/jobs are process-local. [FastAPI containers](https://fastapi.tiangolo.com/deployment/docker/)

## Spotify compatibility found during review

The February 2026 development-mode migration renamed playlist `/tracks` endpoints to `/items`, renamed nested `track` response fields to `item`, and removed bulk `GET /tracks`. Playlist details are limited to owned or collaborative playlists. The installed Spotipy 2.26.0 already uses `/items`, but this repository still assumes the old response shape and fetches bulk track details before writing. Handle both response shapes and remove that extra lookup. Development-mode app owners need Premium and new apps have a five-user limit. [Spotify migration guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide)

The old save path replaces the playlist using only successfully analyzed tracks, and sorting uses a set of IDs. This can drop failed tracks and duplicate occurrences. Use Spotify's positional reorder operation with playlist snapshots, preserve every original occurrence, and keep unanalyzed items in their original positions. A failed save may leave a partial order, but must not remove songs. Check for changes since analysis before saving. [Update playlist items](https://developer.spotify.com/documentation/web-api/reference/reorder-or-replace-playlists-items)

## Existing UX audit

The app is one Streamlit page with a credential sidebar, playlist selector, first-song selector, sorted/original tabs, optional transition table/chart, and an explicit save button. Its theme is Spotify green with a sans-serif font. There are no public content routes, analytics events, or custom brand assets to migrate. Replace the sidebar setup form with server configuration and one Spotify connect button. Keep preview and save separate. Preserve detailed song information behind a simple disclosure; use the user's shadcn preset for the new visual system. Design settings: predictable layout, little motion, low density, corresponding to 3 / 2 / 3 in the frontend design skill. That skill applies to the connect screen and visual basics; the song tables and product workflow use shadcn's own patterns.

## Strict tooling follow-up

Updated the standalone uv installation from 0.12.6 to the current 0.12.10 using `uv self update`; verified Ruff 0.16.6 and ty 0.0.78 against their package releases. The project requires uv 0.12.10 or newer. Ruff selects all rules with only formatter/docstring conflicts and explicit existing-function complexity exemptions. ty supports `all = "error"`; the configuration enables that and treats warnings as failures for app and tests. [uv upgrades](https://docs.astral.sh/uv/getting-started/installation/#upgrading-uv), [Ruff configuration](https://docs.astral.sh/ruff/configuration/), [ty configuration](https://docs.astral.sh/ty/reference/configuration/)

Current Starlette TestClient prefers `httpx2`; ordinary `httpx` is deprecated there. Use `httpx2` in the development group for the offline HTTP checks. [TestClient docs](https://starlette.dev/testclient/)
