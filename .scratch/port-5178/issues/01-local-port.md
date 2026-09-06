# Use browser port 5178

Status: resolved
Type: task

Use port 5178 for Vite and related local launch and Spotify callback settings. Keep the API proxy target on its separate port 8000.

## Comments

Update Vite development and preview, Task commands, Python's callback default, environment setup, Docker's published port, tests and setup docs. Verify startup and the API proxy on 5178, then run the repository checks.

## Answer

All local browser entry points and default Spotify callbacks now use `http://127.0.0.1:5178`. Vite's API proxy and Docker's internal listener use port 8000. Updated the local `.env` callback without changing credentials.

`task check` passed all 21 tests, lint, formatting, type checks and the production build. `git diff --check` passed. Started `task dev` and verified the frontend, proxied health endpoint, OAuth redirect URI and session cookie over HTTP. Verified Python's default and explicit callback override, Vite preview's resolved port/proxy/strict-port settings, and the rendered Docker Compose port/callback configuration. Stopped the temporary development servers after verification.

Spotify's external app settings must register `http://127.0.0.1:5178/api/auth/callback`. No live Spotify authentication or Docker container build was performed.
