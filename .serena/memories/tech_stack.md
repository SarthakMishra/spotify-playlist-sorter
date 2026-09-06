# Runtime and tooling

- FastAPI serves the Vite build through native `app.frontend`. `/api` has a separate 404 route so unknown API URLs never return SPA HTML.
- Spotipy OAuth caches are per-session and server-only. Login rotates the opaque cookie; POST requests require the session CSRF header. The public redirect URI controls the Secure cookie flag.
- Vite proxies `/api` to FastAPI on port 8000 locally. Use browser port 5178 for development, preview, the built app and Docker. Register `http://127.0.0.1:5178/api/auth/callback` with Spotify.
- The Docker build uses Node only to compile the frontend, then copies the bundle into a non-root Python runtime with ffmpeg and libsndfile. The working directory must be writable for the analysis cache.
- Python dependency versions live in `pyproject.toml`/`uv.lock`; frontend versions and pnpm version live in `frontend/package.json`/`pnpm-lock.yaml`. Use uv for Python and pnpm for frontend work.
- CI checks both stacks and builds the frontend before the existing main/tag/manual image publishing step; pull requests run checks without publishing.
