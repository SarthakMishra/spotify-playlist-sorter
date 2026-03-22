# ---------- builder ----------
FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim AS builder

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Strip tests and caches from the venv
RUN find /app/.venv -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; \
    find /app/.venv -type d -name "tests" -exec rm -rf {} + 2>/dev/null; \
    find /app/.venv -type d -name "test" -exec rm -rf {} + 2>/dev/null; \
    rm -rf /app/.venv/lib/python3.13/site-packages/pyarrow*; \
    rm -rf /app/.venv/lib/python3.13/site-packages/pydeck*; \
    true

# ---------- runtime ----------
FROM python:3.13-slim-trixie

LABEL org.opencontainers.image.source="https://github.com/SarthakMishra/spotify-playlist-sorter"
LABEL org.opencontainers.image.description="Spotify Playlist Sorter - Streamlit App"

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg libsndfile1 curl && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

EXPOSE 8501
HEALTHCHECK CMD ["curl", "-f", "http://localhost:8501/_stcore/health"]
ENTRYPOINT ["streamlit", "run", "app/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
