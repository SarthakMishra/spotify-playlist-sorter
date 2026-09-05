# Completion checks

Run `task check` from the repository root, followed by `git diff --check`. The Taskfile defines individual checks for Ruff, ty, Oxlint, Oxfmt, TypeScript and the build.

- Offline tests use real sorting and cookie handling with external I/O mocked. They cover OAuth state/replay, session isolation, CSRF, stale previews, new Spotify response fields, duplicate/unchecked song preservation, interrupted writes and SPA fallback.
- After frontend changes, walk the affected browser flow in light/dark modes and a narrow viewport. Check keyboard access, visible labels and loading/error states.
- For Compose changes, run `docker compose config --quiet`. For Docker changes, build the image and check its health endpoint and a browser route.
- Live Spotify authentication, YouTube extraction and actual playlist writes need external services; offline checks do not validate those integrations.
- For Serena configuration changes, run `serena project index` and `serena project health-check`; for memory changes, run `serena memories check` and inspect stale references.
