# Project commands

Run from the repository root:

- Install locked dependencies: `uv sync --locked`.
- Start the UI: `task run`, equivalent to `uv run streamlit run app/app.py`.
- Apply Ruff fixes, format, and check types: `task fix`.
- `task lint` also modifies source because it invokes Ruff with unsafe fixes. Use the non-mutating checks in `mem:task_completion` for verification.
- Start the published container: `docker compose up`.
- Build current source: `docker build -t spotify-playlist-sorter .`.
- Refresh Serena's local symbol cache: `serena project index`.
- Check Serena symbol tools: `serena project health-check`.
- Check memory references: `serena memories check`; inspect its report because this command always exits zero.
