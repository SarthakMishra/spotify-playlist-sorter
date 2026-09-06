# Configure Zed and remove unused stubs

Status: resolved
Type: task

Use ty and Ruff for Python, Oxlint and Oxfmt for frontend files, and enable format on save in project settings. Delete `typings/` only if the current tooling does not use it.

## Comments

`uv run ty check -vv` passes with only the repository root and virtual environment on its import search paths. No active configuration adds `typings/`; its six Spotipy stubs were generated for Pyright. Remove their stale references from agent documentation.

Use the frontend's installed Oxc binaries because the Zed extension only checks a workspace-root `package.json`. Keep Zed's default frontend language services for completion and navigation.

## Answer

Added `.zed/settings.json` with ty and Ruff for Python, Oxlint and Oxfmt for frontend files, and format on save. Oxc commands use the frontend's pnpm installation. Oxlint explicitly loads the frontend lint and TypeScript configs; Oxfmt discovers the frontend formatter config. Added Zed setup instructions to README.

Deleted all six unused Spotipy stubs and removed stale references from AGENTS.md and the tooling memory. A ty language-server definition request resolves `spotipy.Spotify` to `.venv/lib/python3.13/site-packages/spotipy/client.py`.

Validation: `task check` passed lint, formatting, type checks, all 44 tests and the production build. JSON parsing, Oxfmt's settings-file check and `git diff --check` passed. Direct LSP requests verified Ruff and Oxfmt formatting, ty type errors and Spotipy resolution, and Oxlint's configured `typescript/no-explicit-any` diagnostic. The local Zed launcher points to a missing executable, so editor save behavior was not checked in the GUI.

Configuration references: [ty in Zed](https://docs.astral.sh/ty/editors/#zed), [Ruff formatting in Zed](https://zed.dev/docs/languages/python#configuring-formatting), and [Oxc extension](https://github.com/oxc-project/oxc-zed).
