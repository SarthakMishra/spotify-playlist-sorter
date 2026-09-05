# Playlist sorter

Put your Spotify songs in a smoother order. Connect Spotify, choose a playlist and a first song, then check the new order before saving.

FastAPI serves the API and the Vite/React Router SPA from one address. The frontend uses shadcn's Luma/Zinc preset `beEgoEQi`, with Inter and Lucide. It follows your device's light or dark theme.

## Run locally

You need Python 3.13+, Node 24 LTS, pnpm 11, [uv](https://docs.astral.sh/uv/getting-started/installation/), ffmpeg and a [Spotify developer app](https://developer.spotify.com/dashboard).

1. Add `http://127.0.0.1:8000/api/auth/callback` to your Spotify app's redirect URIs.
2. Copy `.env.example` to `.env` and fill in the Spotify client ID and secret. Existing `.env` files can stay; update their redirect URI if it still points to Streamlit.
3. Install and run:

```bash
uv self update
uv sync --locked
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend build
uv run uvicorn app.app:app --host 127.0.0.1 --port 8000 --no-access-log
```

Open **http://127.0.0.1:8000**. With [Task](https://taskfile.dev/), use `task setup` and `task run` instead. API documentation is at `/docs`.

If Spotify says `redirect_uri: Not matching configuration`, open your app in the Spotify Developer Dashboard, choose **Settings**, and save `http://127.0.0.1:8000/api/auth/callback` under **Redirect URIs**. Include `/api/auth/callback` with no trailing slash. Check the app whose client ID matches your `.env`. Opening the app at `localhost` automatically switches login to `127.0.0.1` so the session cookie reaches the callback.

Credentials and Spotify tokens stay on the server. The browser receives an opaque HttpOnly session cookie. The old credential form and `.spotify_credentials` file are no longer used.

## Development

Run `task dev` to start FastAPI and Vite with reload. Open **http://127.0.0.1:5173** and register `http://127.0.0.1:5173/api/auth/callback` in your Spotify app too. Vite proxies `/api` to FastAPI; the callback returns through the same browser origin. `task dev` sets the local callback for you.

Without Task, run these in separate terminals:

```bash
SPOTIFY_REDIRECT_URI=http://127.0.0.1:5173/api/auth/callback uv run uvicorn app.app:app --reload --no-access-log
pnpm --dir frontend dev
```

The latest uv checked for this migration is **0.12.10**. Python tools are installed in the uv development group: Ruff **0.16.6** and Astral ty **0.0.78**. The frontend uses Oxlint **1.81.0** with type-aware checks, Oxfmt **0.66.0**, and TypeScript **7.0.2**. `pnpm-lock.yaml` and `uv.lock` keep installs repeatable. ESLint and Prettier are not part of the toolchain.

```bash
task check       # lint, formatting, types, offline tests, production build
task fix         # safe lint fixes and formatting
```

The individual checks are:

```bash
uv run ruff check app tests
uv run ruff format --check app tests
uv run ty check
uv run python -m unittest discover -s tests -v
pnpm --dir frontend check
pnpm --dir frontend build
```

Ruff enables all rules, with docstring/formatter conflicts excluded and narrow complexity exceptions on the existing audio algorithms. ty treats all diagnostics as errors. Oxlint checks correctness, suspicious code, performance, hooks, accessibility and unsafe TypeScript operations; warnings fail the check. TypeScript enables strict mode, checked indexing, exact optional properties and unused/unreachable code checks. All owned source, including shadcn components, is checked. `skipLibCheck` skips third-party declaration internals because Recharts' Redux dependency currently fails TypeScript 7's exact optional checks; it does not skip application code.

## Docker

```bash
docker compose up --build
```

Open **http://127.0.0.1:8000**. Compose reads Spotify settings from `.env`. The build compiles the frontend with pnpm and copies the bundle into the Python image; Node is not needed at runtime. The container runs as a non-root user.

For a public deployment, set `SPOTIFY_REDIRECT_URI=https://your-domain/api/auth/callback`, register that exact URI with Spotify, and put the service behind HTTPS. This also enables Secure cookies. Spotify does not accept `localhost` redirect URIs. [Spotify's redirect rules](https://developer.spotify.com/documentation/web-api/concepts/redirect_uri)

Run **one server worker**. Sessions and jobs live in memory, expire after 24 hours, and are cleared on restart. Analysis runs one playlist at a time, with its existing parallel song downloads. Use a shared session store and durable job queue before adding workers or replicas. The analysis cache survives local restarts; container replacement discards it unless you persist it separately.

Spotify's current development mode requires the app owner to have Premium and limits new apps to five users. Wider public access requires the appropriate Spotify access approval. [Spotify migration guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide)

## How sorting works

The existing yt-dlp, soundfile and NumPy pipeline analyzes the first 30 seconds of a YouTube audio match. It estimates musical key, speed and energy, then orders songs from your chosen first song using the existing weighted transition score. These are estimates, and YouTube matching can fail. Successfully analyzed songs are cached locally.

Previewing never changes Spotify. Saving moves existing playlist items and checks the playlist snapshot first. Duplicate songs are kept. Songs that cannot be analyzed, local files and unavailable items keep their positions. If Spotify stops responding during a save, some moves may already be saved; the app asks you to check the playlist again. It never replaces the playlist with a partial list.

Set `YOUTUBE_COOKIES_FILE` to an optional Netscape-format cookie export if YouTube requires it. Cookie inputs remain read-only. The Docker Compose file shows the optional mount.

Offline tests cover login state, sessions, CSRF, preview versions, duplicate and unchecked song preservation, failed saves, SPA routing and cookie handling. They do not exercise live Spotify login or YouTube downloads.

Research and component registry comparisons are in [frontend research](docs/frontend-research.md) and [backend research](docs/backend-research.md).

## License

[MIT](LICENSE)
