# Spotify Playlist Sorter

Sort your Spotify playlists for smooth DJ-style transitions using harmonic mixing (Camelot wheel), BPM matching, and energy flow.

Audio analysis runs entirely locally via **yt-dlp** + **numpy** — no third-party audio API required.

**[Live Demo](https://spotify-playlist-sorter.streamlit.app)**

## Setup

**Prerequisites:** Python 3.13+, [ffmpeg](https://ffmpeg.org/), a [Spotify Developer App](https://developer.spotify.com/dashboard) with redirect URI `http://127.0.0.1:8501`

```bash
git clone https://github.com/SarthakMishra/spotify-playlist-sorter.git
cd spotify-playlist-sorter
uv sync
task run         # or: uv run streamlit run app/app.py
```

Enter your Spotify Client ID and Secret in the app UI, authenticate, pick a playlist, and sort.

### Docker

```bash
docker compose up
```

The app will be available at `http://localhost:8501`. Pass your Spotify credentials via environment variables or the app UI:

```bash
SPOTIFY_CLIENT_ID=your_id SPOTIFY_CLIENT_SECRET=your_secret docker compose up
```

## How It Works

For each track, yt-dlp downloads 30 seconds of audio from YouTube, then lightweight numpy-based analysis extracts:

- **Key & mode** — Krumhansl-Kessler chromagram correlation, mapped to Camelot notation
- **BPM** — onset-strength autocorrelation
- **Energy** — RMS energy, normalized across the playlist

A greedy algorithm orders tracks starting from a user-chosen anchor, maximizing a weighted transition score (50% key compatibility, 30% BPM similarity, 20% energy flow).

## Development

```bash
task fix         # auto-fix, format, and type-check
task lint        # ruff check + ty
task lint:format # ruff format
```

**Toolchain:** [ruff](https://docs.astral.sh/ruff/) (linter + formatter) · [ty](https://github.com/astral-sh/ty) (type checker) · [uv](https://docs.astral.sh/uv/) (package manager)

## License

[MIT](LICENSE)
