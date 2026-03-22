# ---------- builder ----------
FROM ghcr.io/astral-sh/uv:python3.13-alpine AS builder

WORKDIR /app

# Install dependencies first (cached layer) — no-editable avoids embedding source paths
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev --no-editable

COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# Strip heavy optional / unused pieces from the venv
RUN find /app/.venv -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; \
    find /app/.venv -type d -name "tests" -exec rm -rf {} + 2>/dev/null; \
    find /app/.venv -type d -name "test" -exec rm -rf {} + 2>/dev/null; \
    rm -rf /app/.venv/lib/python3.13/site-packages/pyarrow*; \
    rm -rf /app/.venv/lib/python3.13/site-packages/pydeck*; \
    rm -rf /app/.venv/lib/python3.13/site-packages/numpy/tests*; \
    rm -rf /app/.venv/lib/python3.13/site-packages/pandas/tests*; \
    true

# ---------- runtime ----------
FROM python:3.13-alpine

LABEL org.opencontainers.image.source="https://github.com/SarthakMishra/spotify-playlist-sorter"
LABEL org.opencontainers.image.description="Spotify Playlist Sorter - Streamlit App"

# libsndfile for soundfile package; symlink needed because ctypes.util.find_library
# does not work on musl and the soundfile package falls back to dlopen("libsndfile.so")
RUN apk add --no-cache libsndfile && \
    ln -s /usr/lib/libsndfile.so.1 /usr/lib/libsndfile.so

COPY --from=mwader/static-ffmpeg:7.1.1 /ffmpeg /usr/local/bin/ffmpeg

# Copy only the venv and app source — uv binary stays in builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/app /app/app
ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

EXPOSE 8501
HEALTHCHECK CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"]
ENTRYPOINT ["streamlit", "run", "app/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
