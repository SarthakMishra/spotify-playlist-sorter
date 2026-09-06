# Playlist sorter

Put your Spotify songs in a smoother order. Connect Spotify, choose a playlist and a listening style, optionally choose the first and last songs, then review the order before saving.

FastAPI serves the API and the Vite/React Router SPA from one address. The frontend uses shadcn's Luma/Zinc preset `beEgoEQi`, with Inter and Lucide. It follows your device's light or dark theme.

## Run locally

You need Python 3.13+, Node 24 LTS, pnpm 11, [uv](https://docs.astral.sh/uv/getting-started/installation/), ffmpeg and a [Spotify developer app](https://developer.spotify.com/dashboard).

1. Add `http://127.0.0.1:5178/api/auth/callback` to your Spotify app's redirect URIs.
2. Copy `.env.example` to `.env` and fill in the Spotify client ID and secret. For an existing `.env`, set `SPOTIFY_REDIRECT_URI=http://127.0.0.1:5178/api/auth/callback`.
3. Install and run:

```bash
uv self update
uv sync --locked
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend build
uv run uvicorn app.app:app --host 127.0.0.1 --port 5178 --no-access-log
```

Open **http://127.0.0.1:5178**. With [Task](https://taskfile.dev/), use `task setup` and `task serve` instead. API documentation is at `/docs`.

If Spotify says `redirect_uri: Not matching configuration`, open your app in the Spotify Developer Dashboard, choose **Settings**, and save `http://127.0.0.1:5178/api/auth/callback` under **Redirect URIs**. Include `/api/auth/callback` with no trailing slash. Check the app whose client ID matches your `.env`. Opening the app at `localhost` automatically switches login to `127.0.0.1` so the session cookie reaches the callback.

Credentials and Spotify tokens stay on the server. The browser receives an opaque HttpOnly session cookie. The old credential form and `.spotify_credentials` file are no longer used.

## Development

Run `task run` or `task dev` to start FastAPI with reload and Vite with frontend hot reload. Open **http://127.0.0.1:5178**. Vite proxies `/api` to FastAPI on port 8000; the callback returns through the same browser origin on port 5178. Both commands set the local callback for you. Use `task serve` to build and serve the production frontend at the same browser address.

Without Task, run these in separate terminals:

```bash
SPOTIFY_REDIRECT_URI=http://127.0.0.1:5178/api/auth/callback uv run uvicorn app.app:app --host 127.0.0.1 --port 8000 --reload --no-access-log
pnpm --dir frontend dev
```

After building, `pnpm --dir frontend preview` also serves on port 5178 and proxies `/api` to the development API. Vite exits if port 5178 is occupied so the Spotify callback stays on the configured port. Run one frontend serving mode at a time.

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

Open **http://127.0.0.1:5178**. Compose maps host port 5178 to container port 8000 and reads Spotify settings from `.env`. The build compiles the frontend with pnpm and copies the bundle and Node runtime into the Python image. yt-dlp uses Node to solve YouTube player challenges. The container runs as a non-root user. Debian slim allows the locked audio-analysis wheels to install without building LLVM.

For a public deployment, set `SPOTIFY_REDIRECT_URI=https://your-domain/api/auth/callback`, register that exact URI with Spotify, and put the service behind HTTPS. This also enables Secure cookies. Spotify does not accept `localhost` redirect URIs. [Spotify's redirect rules](https://developer.spotify.com/documentation/web-api/concepts/redirect_uri)

Run **one server worker**. Sessions and jobs live in memory, expire after 24 hours, and are cleared on restart. Analysis runs one playlist at a time, with its existing parallel song downloads. Use a shared session store and durable job queue before adding workers or replicas. The analysis cache survives local restarts; container replacement discards it unless you persist it separately.

Spotify's current development mode requires the app owner to have Premium and limits new apps to five users. Wider public access requires the appropriate Spotify access approval. [Spotify migration guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide)

## How sorting works

The yt-dlp resolver searches lightweight metadata, then inspects at most three promising videos. It checks title, credited artists, recording version and duration before accepting a source. Matching uses the song title, duration and available album/artist credits. Any listed artist can support a match; the first Spotify credit is not assumed to be the singer. Verified-channel uploads with strong title/duration agreement can serve as best-effort matches when their artist fields are missing. It chooses the best eligible upload even when several candidates have close scores. Additional artist or producer credits improve ranking but are not required. Conflicting explicit artist/version metadata and substantially different durations are excluded. Upload duration may differ by up to 8%, capped at twenty seconds, to accommodate modest differences between releases. Matching remains an estimate; YouTube intros and outros can differ from Spotify. Missing matches and YouTube access failures have separate explanations. Librosa 1.0 measures the complete recording, up to twenty minutes, retaining five-second summaries and the actual beginning, body and ending. Missing rhythm or key evidence stays unknown. Estimated intensity combines audio level and rhythmic activity; it does not measure mood.

Smooth prioritizes comfortable changes between each ending and the next beginning. More variety gives artist spacing and changes in texture more influence. Both use confidence-aware tempo, intensity, texture and chroma comparisons, with a bounded search over complete playlist entries. The original order, adjusted for your endpoint choices, remains the baseline and wins ties. These objectives still need listening validation.

First and last songs are optional and refer to specific occurrences. A fixed entry cannot give its position to another song. Switching styles reuses the current analysis; identical and unchanged results are shown honestly, and unchanged orders do not trigger saves. Above 1,000 entries, the app applies explicit endpoint choices and preserves the remaining relative order with a limited-search message. [Implementation and measured timings](docs/arrangement-benchmarks.md).

Audio measurements live in `app/audio_analysis.py`; matching, caching and ordering remain in `app/playlist_sorter.py`.

Successful analyses are cached with recording metadata, source evidence, extractor settings and version identifiers. Old unversioned results are ignored. Duplicate entries share recording work, and playlist-relative intensity is calculated without changing cached raw measurements. Analysis processes at most two recordings concurrently and writes atomic cache checkpoints. Cached sources are not checked for upstream changes on every use; metadata matching also cannot prove that two recordings contain identical audio.

Previewing never changes Spotify. The preview shows every playlist entry at the position it will occupy after saving. Duplicate songs keep separate identities, and the first-song selector labels each occurrence by its original position. Songs that cannot be analyzed, local files, episodes and unavailable items stay visible in their original positions with a reason. Transitions involving those entries are marked as not assessed. With fewer than two movable songs, the app shows the unchanged playlist and offers another check.

The complete song list appears as soon as metadata loads, while individual entries show whether a recording is being found or its audio is being measured. Finished checks and successful measurements have separate counts. You can leave and return to the current job; an interrupted check retains the last-loaded list for reference.

The Suggested and Original tabs show the complete orders. Compare plots each song's estimated intensity over its full duration, with the original order dashed and the suggestion solid. Missing intensity stays a gap; missing or invalid duration disables the time chart. Timing assumes full playback with crossfade off. Expand the text tables for exact song times, or the secondary measurements for tempo and key. The review shows assessment coverage and at most three supported listening notes, without presenting a musical-quality percentage.

Saving moves existing playlist items. Before and after the moves, it reads the complete playlist between matching Spotify snapshots and checks the order, duplicate entries and fixed items. Saved appears only after verification. If a move or verification fails, some songs may have moved; check the playlist again before another save. Moves are never automatically replayed or rolled back.

After a verified save, **Restore previous order** undoes the most recent save in this session using the same moves and verification. It first checks that Spotify still matches the saved result. The option expires after use, a new playlist analysis, sign-out, session expiry or a server restart; an observed external edit or uncertain write also removes it. Arranging another preview keeps the restore target until a new save succeeds. This is one level of recovery, with no permanent history.

## Optional YouTube cookies

Cookies are optional. Without them, checking continues anonymously. They can help the app find the correct recording when YouTube requires sign-in; we use them for YouTube searches and audio downloads. They do not prove that two recordings are identical.

Open **YouTube access** in the app to add or remove a cookie export. Uploads stay in your server-side session, contain only YouTube cookies after validation, and are not written to disk. Signing out, expiry or a restart removes the session. Choose **Use without cookies** to explicitly use anonymous access. After changing access, return to your playlist and choose **Check songs again** or **Check again**. Successful cached recordings are reused.

To export from Chrome:

1. Install [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc), the extension recommended by [yt-dlp's FAQ](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp), and allow it in Incognito in Chrome's extension settings.
2. Open one Incognito window and sign in to YouTube. In that same tab, open `https://www.youtube.com/robots.txt`.
3. Export only `youtube.com` cookies in Netscape text format. Do not select JSON or all sites.
4. Close the Incognito window and select the exported file in the app. Avoid reopening that session; YouTube rotates cookies in open browser sessions. [Official export guidance](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies).

Cookie files can grant access to your account. Upload only to a server you trust. The app rejects malformed or expired-only files without printing their contents. An invalid configured file gives a setup error instead of silently changing account context.

For direct browser access on the same computer as the backend, set these in `.env` and restart:

```dotenv
YOUTUBE_BROWSER=chrome
# Optional profile name or local path:
YOUTUBE_BROWSER_PROFILE=Default
# Optional Linux keyring override; normally leave blank:
YOUTUBE_BROWSER_KEYRING=
```

Alternatively, set `YOUTUBE_COOKIES_FILE` to an existing Netscape export. A configured file takes precedence over the browser. Both sources stay read-only; the app takes one private cookie snapshot per checking job, not one browser read per song. Linux Chrome keyring support is included through SecretStorage; the desktop keyring must be accessible to the server process. If Chrome is locked, decryption fails, or the app is running remotely/in Docker, use the extension upload. A webpage cannot read a remote visitor's browser profile. Docker Compose also shows the optional read-only file mount.

## YouTube reliability and checking speed

`yt-dlp[default]` supplies version-compatible challenge scripts, and the app explicitly enables Node. Run `uv sync --locked` after pulling this change; Node 24 must be available to the backend. The Docker image includes it. [yt-dlp's JavaScript setup](https://github.com/yt-dlp/yt-dlp/wiki/EJS).

Search details and downloads both request audio-only formats. Checking first reuses the selected video's extracted formats. If a download fails, it retries once with fresh extraction and fresh media URLs, then tries the next eligible candidate. HTTP and fragment retries remain bounded, and missing audio fragments fail the recording instead of being silently skipped. Two recording workers remain the limit. A shared sign-in, cookie, player or rate-limit error stops queued source requests and explains what to fix. If YouTube limits requests, wait before retrying; cookies do not remove those limits. The default clients remain in use. A PO-token provider is a follow-up only if observed failures require it. [Current YouTube guidance](https://github.com/yt-dlp/yt-dlp/wiki/Extractors).

Safe recording diagnostics retain search, metadata, download and measurement timings plus candidate counts. They exclude cookies and signed media URLs. Successful analyses accepted by resolver version 2 are retained because they passed stricter matching rules. New results use version 3; failed searches are retried when you check again. There is no persistent cache of failed searches, so a fresh check can benefit from corrected access.

The [research and measured checks](docs/ytdlp-reliability-research.md#implemented-result-and-validation) explain the request reduction and its limits. No live speed multiplier or match-accuracy percentage has been measured.

Offline tests cover login state, sessions, CSRF, preview versions, duplicate and unchecked song preservation, failed saves, SPA routing and cookie handling. Generated audio also checks pitch, resampling level, real boundaries, silence, rhythm uncertainty and bounded loading. Metadata fixtures check rejected variants, ambiguous matches, fallback downloads and cache invalidation/checkpoints. Review checks cover metadata/progress before completion, interrupted checks, bounded evidence-based notes and duration-aware comparisons. These tests do not exercise live Spotify login or YouTube downloads.

Research and component registry comparisons are in [frontend research](docs/frontend-research.md) and [backend research](docs/backend-research.md).

The [librosa reference and measured extraction results](docs/librosa-analysis-research.md) document the current analysis. The [source feasibility report](docs/audio-source-feasibility.md) records the unresolved live-integration and recording-permission questions; development validation uses generated audio and mocked services.

## License

[MIT](LICENSE)
