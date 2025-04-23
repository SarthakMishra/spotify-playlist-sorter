# Spotify Playlist Sorter

A Streamlit app that sorts your Spotify playlists based on musical key compatibility (Camelot wheel), BPM (tempo), and energy levels to create smooth transitions between tracks.

## Features

- Loads playlist data directly from Spotify
- Analyzes tracks using songdata.io
- Sorts tracks based on:
  - Harmonic mixing (Camelot wheel)
  - BPM (tempo) similarity
  - Energy level transitions
- Updates playlist order on Spotify
- Provides detailed transition analysis
- User-friendly Streamlit interface

## Live Demo

Try the app at: [https://spotify-playlist-sorter.streamlit.app](https://spotify-playlist-sorter.streamlit.app)

## Local Setup

1. Clone the repository:
```bash
git clone https://github.com/SarthakMishra/spotify-playlist-sorter.git
cd spotify-playlist-sorter
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a Spotify Developer Application:
   - Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
   - Create a new application
   - Get your Client ID and Client Secret
   - Add `http://localhost:8501/callback` to your app's Redirect URIs in the settings

4. Configure environment variables:
   - Copy `.env.template` to `.env`
   - Fill in your Spotify API credentials in `.env`

## Usage

### Streamlit App (Recommended)

1. Run the Streamlit app:
```bash
streamlit run app/app.py
```

2. Open your browser at `http://localhost:8501`

3. Follow the instructions in the app:
   - Authenticate with Spotify
   - Select a playlist to sort
   - Choose an anchor track
   - Review the transition analysis
   - Update your playlist with the optimized order

### Jupyter Notebooks (Alternative)

The original Jupyter notebooks are still available in the `notebooks` directory:

1. First, run `notebooks/spotify_auth.ipynb` to:
   - Start a local authentication server
   - Automatically open your browser for Spotify authorization
   - View a list of your playlists and their IDs
   - Note: For notebooks, add `http://127.0.0.1:8888/callback` to your Spotify app's Redirect URIs

2. Then, run `notebooks/spotify_playlist_sorter.ipynb`:
   - Enter your chosen playlist ID
   - Review the transition analysis
   - Update your playlist with the optimized order

## How it Works

The sorter uses several factors to create optimal transitions:

1. **Camelot Wheel**: Ensures harmonic compatibility between tracks
2. **BPM Matching**: Minimizes tempo changes between tracks
3. **Energy Flow**: Creates smooth energy level transitions
4. **Opening Track**: Selects a high-energy, popular track to start the playlist

## Deployment

This app is designed to be deployed to Streamlit Cloud. To deploy your own version:

1. Fork this repository
2. Connect your GitHub account to Streamlit Cloud
3. Deploy the app, pointing to `app/app.py`
4. Add your Spotify API credentials to the Streamlit Cloud secrets

## Notes

- The app requires Spotify API access and will modify your playlists
- Always make a backup of important playlists before sorting
- Rate limits apply to Spotify API calls
- **Important Note**: This project scrapes track attributes (BPM, key, energy) from songdata.io as the Spotify Web API's "Get Track's Audio Features" endpoint has been deprecated. Due to the nature of web scraping, this project might not work if the structure of songdata.io changes. If you encounter any issues due to website structure changes, please feel free to open a Pull Request with the necessary updates.
