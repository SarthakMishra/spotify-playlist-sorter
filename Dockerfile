FROM python:3.13-slim

LABEL org.opencontainers.image.source="https://github.com/SarthakMishra/spotify-playlist-sorter"
LABEL org.opencontainers.image.description="Spotify Playlist Sorter - Streamlit App"

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY .streamlit .streamlit
COPY app/ app/

EXPOSE 8501

HEALTHCHECK CMD ["curl", "-f", "http://localhost:8501/_stcore/health"]

ENTRYPOINT ["streamlit", "run", "app/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
