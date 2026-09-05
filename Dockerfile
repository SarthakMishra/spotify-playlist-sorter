FROM node:24-alpine AS frontend
WORKDIR /web
RUN corepack enable && corepack prepare pnpm@11.24.0 --activate
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM ghcr.io/astral-sh/uv:0.12.10-python3.14-alpine AS builder
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev --no-editable

FROM python:3.14-alpine
LABEL org.opencontainers.image.source="https://github.com/SarthakMishra/spotify-playlist-sorter"
LABEL org.opencontainers.image.description="Spotify Playlist Sorter"
RUN apk add --no-cache libsndfile && \
    ln -s /usr/lib/libsndfile.so.1 /usr/lib/libsndfile.so && \
    adduser -D -u 10001 sorter && mkdir /app && chown sorter /app
COPY --from=mwader/static-ffmpeg:9.0.1 /ffmpeg /usr/local/bin/ffmpeg
COPY --from=builder /app/.venv /app/.venv
COPY app /app/app
COPY --from=frontend /web/dist /app/frontend/dist
ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app
USER sorter
EXPOSE 8000
HEALTHCHECK CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"]
ENTRYPOINT ["uvicorn", "app.app:app", "--host=0.0.0.0", "--port=8000", "--workers=1", "--no-access-log"]
