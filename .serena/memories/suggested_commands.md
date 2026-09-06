# Project commands

- `task setup` installs locked Python and pnpm dependencies.
- `task run` and `task dev` run Vite and FastAPI together on browser port 5178, with the matching local OAuth callback. `task serve` builds and serves the SPA/API on port 5178.
- `task check` runs non-mutating lint, formatting, types, offline tests and the production build. `task fix` applies safe fixes and formatting, then checks the result.
- `docker compose up --build` builds current source; Compose includes a build definition.
- Serena maintenance commands are `serena project index`, `serena project health-check` and `serena memories check`. Inspect the memory report because that command always exits zero.
