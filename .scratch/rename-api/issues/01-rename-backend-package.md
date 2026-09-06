# Rename the backend package to api

Status: resolved
Type: task

Move `app/` to `api/` and update repository imports, test patches, launch commands,
Docker packaging, checks, scripts, and documentation links. Preserve HTTP routes,
OAuth callbacks, session behavior, cache location, frontend serving, and Git history.
Use `api.app:app` as the server entry point.

## Validation

Run `task check` and `git diff --check`. Compare the OpenAPI schema and health
response before and after the move, check static serving, and smoke-test Docker.
Confirm Git detects all six Python files as renames.

## Comments

The working tree already contained unrelated edits. Preserve them while updating
the affected paths. Legacy external `app.*` imports are outside the clean rename
unless requested.

## Answer

Moved all six Python files with `git mv` and updated the repository references.
Git detects four files at 100% similarity and the two files with changed imports
at 99%. Existing uncommitted edits were preserved.

Validation passed:

- `task check`, including all 44 offline tests and the production frontend build.
- `git diff --check` and `git diff --cached --check`.
- Identical OpenAPI schema and health response before and after the move.
- New `api.app:app` import, unchanged cache path, built assets, browser navigation
  fallback, and JSON 404 responses for unknown API paths.
- Offline Spotipy endpoint and payload checks.
- Docker build and the existing container smoke script with networking disabled,
  including Node 24, generated audio analysis, non-root execution, API and SPA.
- Docker Compose configuration still exposes the existing `app` service.

External launch configurations must use `api.app:app`; external Python imports
must use `api.*`. No legacy import shim was added.
