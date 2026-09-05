# Code conventions

- Follow `pyproject.toml` for Ruff and ty configuration. Existing code uses annotated signatures, future annotations, Google-style docstrings, double quotes, and 120-character formatting.
- Runtime imports between app modules are unqualified sibling imports. ty's `extra-paths = ["app"]` and direct-check `PYTHONPATH=app` must agree with Streamlit's script execution.
- Keep logging in the backend and Streamlit rendering/session-state mutations in `app/app.py` or the existing auth flow. Playlist analysis accepts a progress callback instead of importing UI behavior into worker functions.
- `.cursor/rules/terminal.mdc` retains obsolete references to pylint and pyright. Actual task commands and `pyproject.toml` use Ruff and ty; treat those files as authoritative.
- Cookie exports, Spotify credentials/token caches, audio files, and analysis caches are local artifacts. Keep cookie inputs read-only; each yt-dlp instance uses its own in-memory copy because yt-dlp saves cookies on close and analysis runs concurrently.
