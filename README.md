# Spotify Playlist Sorter

A Python tool that sorts your Spotify playlists based on musical key compatibility (Camelot wheel), BPM (tempo), and energy levels to create smooth transitions between tracks.

## Features

- Loads playlist data directly from Spotify
- Analyzes tracks using Spotify's audio features API
- Sorts tracks based on:
  - Harmonic mixing (Camelot wheel)
  - BPM (tempo) similarity
  - Energy level transitions
- Updates playlist order on Spotify
- Provides detailed transition analysis

## Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/playlist-sorter.git
cd playlist-sorter
```

2. Set up the virtual environment:
```bash
uv venv
source .venv/bin/activate  # On Windows, use: .venv\Scripts\activate
uv sync
```

3. Create a Spotify Developer Application:
   - Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
   - Create a new application
   - Get your Client ID and Client Secret
   - Add `http://127.0.0.1:8888/callback` to your app's Redirect URIs in the settings
     - Note: Using `localhost` is deprecated, use the loopback IP address `127.0.0.1` instead

4. Configure environment variables:
   - Copy `.env.template` to `.env`
   - Fill in your Spotify API credentials in `.env`

## Usage

1. First, run `spotify_auth.ipynb` to:
   - Start a local authentication server
   - Automatically open your browser for Spotify authorization
   - View a list of your playlists and their IDs
   - Note: The authentication process will open a browser window and redirect back to your local server

2. Then, run `spotify_playlist_sorter.ipynb`:
   - Enter your chosen playlist ID
   - Review the transition analysis
   - Update your playlist with the optimized order

## How it Works

The sorter uses several factors to create optimal transitions:

1. **Camelot Wheel**: Ensures harmonic compatibility between tracks
2. **BPM Matching**: Minimizes tempo changes between tracks
3. **Energy Flow**: Creates smooth energy level transitions
4. **Opening Track**: Selects a high-energy, popular track to start the playlist

## Notes

- The tool requires Spotify API access and will modify your playlists
- Always make a backup of important playlists before sorting
- Rate limits apply to Spotify API calls
- The authentication process requires a web browser and will open a new window
- Make sure no other application is using port 8888 when running the authentication notebook
- **Important Note**: This project scrapes track attributes (BPM, key, energy) from songdata.io as the Spotify Web API's "Get Track's Audio Features" endpoint has been deprecated. Due to the nature of web scraping, this project might not work if the structure of songdata.io changes. If you encounter any issues due to website structure changes, please feel free to open a Pull Request with the necessary updates. 