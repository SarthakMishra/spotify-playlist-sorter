# Spotify Playlist Sorter

Reorder a Spotify playlist for smoother transitions or more variety. Choose a playlist, optionally pick the first and last songs, then review the suggested order before saving.

The app uses FastAPI and React. Spotify credentials and tokens stay on the server; the browser gets an HttpOnly session cookie.

## Run locally

Install Python 3.13+, Node 24, pnpm 11, [uv](https://docs.astral.sh/uv/getting-started/installation/), ffmpeg and [Task](https://taskfile.dev/).

1. Create a [Spotify developer app](https://developer.spotify.com/dashboard).
2. Add `http://127.0.0.1:5178/api/auth/callback` to its redirect URIs.
3. Copy `.env.example` to `.env` and fill in `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET`. Keep `SPOTIFY_REDIRECT_URI` set to the callback above.
4. Install dependencies and start the app:

```bash
task setup
task serve
```

Open http://127.0.0.1:5178. API documentation is at `/docs`.

Without Task, use:

```bash
uv sync --locked
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend build
uv run uvicorn api.app:app --host 127.0.0.1 --port 5178 --no-access-log
```

If Spotify reports `redirect_uri: Not matching configuration`, check that the app matching your client ID has the exact callback above saved in its settings. Use `127.0.0.1`, include `/api/auth/callback`, and leave off the trailing slash.

## Using the app

Connect Spotify, choose a playlist and check its songs. The app finds likely YouTube recordings and uses librosa to measure tempo, intensity, texture and key. Matching can be wrong, and estimated intensity describes audio level and rhythmic activity, not mood.

- **Smooth** favors smaller changes between one song's ending and the next song's beginning.
- **More variety** gives artist spacing and changes in texture more weight.

Switching styles reuses the analysis. First and last songs are optional. Duplicate songs remain separate playlist entries. Songs without usable analysis, local files, episodes and unavailable items stay visible in their original positions with a reason. Above 1,000 entries, the app applies your endpoint choices and keeps the remaining relative order.

Review the Suggested and Original tabs, or use Compare to see intensity over listening time. The chart assumes full playback with crossfade off. Missing measurements remain gaps. Listen to the result before deciding whether the arrangement works for you.

Previewing never changes Spotify. Saving moves existing entries and verifies the complete order before reporting success. If a save fails, some entries may already have moved. Check the playlist again before retrying; the app does not automatically replay or roll back moves.

After a successful save, **Restore previous order** can undo it once, provided Spotify still matches the saved result. The option ends after use, a new playlist analysis, sign-out, session expiry or a server restart. An observed external edit or uncertain save also removes it. There is no permanent undo history.

## YouTube requirements

The app looks up recordings anonymously. Node must be available to the backend for yt-dlp's YouTube player challenges. If YouTube limits requests, wait before retrying. Checks process at most two recordings at once and cache successful analyses. Failed searches are retried on the next check.

## Development

Run commands from the repository root:

| Command | Purpose |
| --- | --- |
| `task setup` | Install locked Python and frontend dependencies |
| `task dev` or `task run` | Start FastAPI and Vite with hot reload |
| `task build` | Type-check and build the frontend |
| `task serve` | Build and serve the app |
| `task test` | Run offline Python regression tests |
| `task check` | Run lint, formatting, type checks, tests and the production build |
| `task fix` | Apply safe lint fixes and formatting, then recheck |

Development uses http://127.0.0.1:5178. Vite proxies `/api` to FastAPI on port 8000, and `task dev` sets the matching Spotify callback. Run one frontend serving mode at a time.

Backend code lives in `api/`, frontend code in `frontend/src/`, and tests in `tests/`. Checks use Ruff, Astral ty, Oxlint, Oxfmt and TypeScript. Tests use mocked services and generated audio; they do not exercise live Spotify login or YouTube downloads.

For Zed, install the [Oxc extension](https://github.com/oxc-project/oxc-zed) and open the repository root after `task setup`. `.zed/settings.json` enables format on save with Ruff for Python and Oxfmt for frontend files, plus ty and Oxlint diagnostics. Select `.venv` as the Python toolchain so Zed uses the project's installed Ruff and ty.

## Docker and deployment

Configure `.env` as above, then run:

```bash
docker compose up --build
```

Open http://127.0.0.1:5178. Compose maps port 5178 to container port 8000. The image includes the built frontend and Node.

For a public deployment, use HTTPS, set `SPOTIFY_REDIRECT_URI=https://your-domain/api/auth/callback`, and register that exact URI with Spotify. HTTPS callbacks enable Secure cookies. Check Spotify's [redirect rules](https://developer.spotify.com/documentation/web-api/concepts/redirect_uri) and [development-mode access requirements](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide) before sharing the app.

Run one server worker. Sessions and jobs live in memory, expire after 24 hours and disappear on restart. Analysis runs one playlist at a time. Multiple workers or replicas need shared session storage and a durable job queue. The analysis cache survives local restarts but needs separate persistence to survive container replacement.

## Further reading

- [Arrangement behavior and benchmarks](docs/arrangement-benchmarks.md)
- [Audio measurements and validation](docs/librosa-analysis-research.md)
- [YouTube matching, retries and diagnostics](docs/ytdlp-reliability-research.md)
- [Audio source feasibility and unresolved permission questions](docs/audio-source-feasibility.md)
- [Frontend research](docs/frontend-research.md) and [backend research](docs/backend-research.md)

## License

[MIT](LICENSE)
