# Completion checks

Run from the repository root:

```bash
task lint:check lint:format:check lint:ty
uv run ruff check tests
uv run ruff format --check tests
PYTHONPATH=app uv run python -m unittest discover -s tests -v
git diff --check
```

- The cookie regression test uses real yt-dlp cookie handling with mocked extraction and audio loading; it requires no network, Spotify credentials, or ffmpeg process. It covers absent, empty, missing, directory, and read-only cookie-file inputs in both search and download.
- For Compose edits, also run `docker compose config --quiet`.
- For Serena configuration changes, run `serena project index` and `serena project health-check`; for memory edits, run `serena memories check` and inspect the report for stale references.
- `.serena/.gitignore` keeps caches, health-check logs, and `project.local.yml` local. Commit shared project configuration and memories.
- Live Spotify authentication, YouTube extraction, and playlist writes require external services; offline checks do not validate those integrations.
