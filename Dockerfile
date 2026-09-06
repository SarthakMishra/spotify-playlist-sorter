FROM node:24-bookworm-slim AS frontend
WORKDIR /web
RUN corepack enable && corepack prepare pnpm@11.24.0 --activate
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.14-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev --no-editable

FROM python:3.14-slim-bookworm
LABEL org.opencontainers.image.source="https://github.com/SarthakMishra/spotify-playlist-sorter"
LABEL org.opencontainers.image.description="Spotify Playlist Sorter"
# Use manylinux wheels for librosa/Numba instead of building LLVM on Alpine.
RUN apt-get update && apt-get install -y --no-install-recommends libsndfile1 libstdc++6 && \
    rm -rf /var/lib/apt/lists/* && \
    useradd --create-home --uid 10001 sorter && mkdir /app && chown sorter /app
COPY --from=frontend /usr/local/bin/node /usr/local/bin/node
COPY --from=mwader/static-ffmpeg:9.0.1 /ffmpeg /usr/local/bin/ffmpeg
COPY --from=builder /app/.venv /app/.venv
COPY api /app/api
COPY --from=frontend /web/dist /app/frontend/dist
ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app
USER sorter
EXPOSE 8000
HEALTHCHECK CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"]
ENTRYPOINT ["uvicorn", "api.app:app", "--host=0.0.0.0", "--port=8000", "--workers=1", "--no-access-log"]
