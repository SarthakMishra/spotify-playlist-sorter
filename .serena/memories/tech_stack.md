# Runtime and tooling

- Python minimum and Ruff/ty target are 3.13; the Docker runtime uses Python 3.14 Alpine. `pyproject.toml` and `uv.lock` are the dependency sources of truth; use uv and the local `.venv`.
- Streamlit provides the UI, pandas the track tables, Plotly the charts, and Spotipy the Spotify API/OAuth client. yt-dlp downloads audio; soundfile and numpy perform local analysis. ffmpeg is a system dependency; Alpine also needs libsndfile.
- Development checks use Ruff and ty. `typings/spotipy/*.pyi` supplies local Spotipy stubs; preserve them when changing API calls or typing configuration.
- `docker compose up` runs the published GHCR image. Local source changes require an explicit image build; Compose has no build step or app-source mount.
- `.github/workflows/publish-image.yml` publishes images on main pushes, version tags, and manual dispatch. It does not run Python validation.
