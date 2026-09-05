# Repository Guidelines

## Project structure and module organization

- `app/app.py` defines FastAPI routes, sessions, jobs, and SPA serving. `app/playlist_sorter.py` handles audio analysis and ordering; `app/spotify_auth.py` handles Spotify authentication.
- `frontend/src/` contains the React/TypeScript app. Put page components in `components/`, shared shadcn controls in `components/ui/`, and API helpers in `lib/`. Static assets live in `frontend/public/`; builds output to `frontend/dist/`.
- `tests/` contains offline Python regression tests. `typings/spotipy/` provides local type stubs; `docs/` contains architecture research.

## Build, test, and development commands

Use Python 3.13+, Node 24, pnpm 11, uv, ffmpeg, and Task. Run these from the repository root:

- `task setup`: install dependencies from `uv.lock` and `frontend/pnpm-lock.yaml`.
- `task dev`: start reloading FastAPI and Vite servers at `http://127.0.0.1:5173`.
- `task build`: type-check and build the frontend.
- `task run`: start reloading FastAPI and Vite servers at `http://127.0.0.1:5173`, like `task dev`.
- `task serve`: build and serve the app at `http://127.0.0.1:8000`.
- `task test`: run offline tests, equivalent to `uv run python -m unittest discover -s tests -v`.
- `task check`: run lint, formatting, type checks, tests, and the production build.
- `task fix`: apply safe lint fixes and formatting, then recheck lint and types.

## Coding style and naming conventions

Python uses four-space indentation, double quotes, a 120-character line limit, type annotations, and Google-style docstrings. Use `snake_case` for functions/modules and `PascalCase` for classes. Ruff and Astral ty enforce Python checks.

TypeScript uses two-space indentation, double quotes, and no semicolons. Follow existing kebab-case component filenames and PascalCase component names. Reuse shadcn controls and theme tokens. Oxlint, Oxfmt, and strict TypeScript enforce frontend checks.

## Testing guidelines

Use `unittest.TestCase`, `test_*.py` files, and `test_*` methods. Mock external I/O; use FastAPI `TestClient` for HTTP contracts. Cover changed behavior, especially session isolation, stale previews, duplicate preservation, and interrupted saves. No numeric coverage threshold or frontend test runner is configured. Check UI changes manually with keyboard navigation, light/dark themes, and narrow viewports.

## Commit and pull request guidelines

Follow the history's Conventional Commits style, such as `feat: ...`, `fix(config): ...`, and `chore(deps): ...`. Keep commits focused. Describe behavior changes, link relevant issues, report validation, and include screenshots for UI changes. Run `task check` and `git diff --check` before review.

## Security and configuration

Copy `.env.example` to `.env`; keep credentials, tokens, cookie exports, and caches untracked. Follow `README.md` for exact Spotify callback URLs. Keep tokens server-side and YouTube cookie inputs read-only. Run one server worker because sessions and jobs live in memory.

## Agent skills

### Issue tracker

Track issues and specs under `.scratch/<feature>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the five default triage roles as issue statuses. See `docs/agents/triage-labels.md`.

### Domain docs

Use single-context domain documentation. See `docs/agents/domain.md` before exploring domain concepts or architectural decisions.
