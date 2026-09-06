# Code conventions

- `pyproject.toml` is authoritative for Ruff and ty. Ruff enables all rules with formatter/docstring conflicts and narrow legacy complexity exceptions. ty enables all diagnostics as errors and checks api plus tests.
- The frontend uses pnpm, Oxlint with type-aware rules, Oxfmt and strict TypeScript. Keep both compiler projects strict. The `skipLibCheck` exception covers dependency declarations, not owned component source; its reason is recorded in README.
- Use the existing shadcn Base Luma components and preset tokens. Plain consumer copy belongs in the frontend; log implementation details on the backend.
- Browser JSON decoding has one documented generic type assertion in the API helper. Request bodies and response models are checked by FastAPI/Pydantic. Spotify credentials and tokens never enter frontend env variables or response payloads.
- Local secrets, cookie exports, downloaded audio and analysis caches remain untracked. Cookie input files are read-only; each yt-dlp instance uses a separate in-memory copy.
- Editor recommendations use Ruff, Astral ty and Oxc. The workspace disables the competing Pylance language server; CLI configuration remains authoritative.
