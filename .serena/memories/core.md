# Project map

- `app/app.py` owns Streamlit session state, OAuth UI, playlist selection, sorting previews, and the explicit Spotify update action.
- `app/spotify_auth.py` owns credential precedence, redirect selection, token refresh, and Spotipy client creation. UI-supplied session credentials take precedence over environment variables and Streamlit secrets.
- `app/playlist_sorter.py` owns Spotify pagination, YouTube candidate selection/download, local audio analysis, transition scoring, greedy ordering, and playlist writes; shared thresholds live in `app/constants.py`.
- Audio features come from local yt-dlp + soundfile + numpy analysis, cached by Spotify track ID in the repository-root `.analysis_cache.json`. Uncached tracks run in a thread pool; Streamlit progress updates run as futures complete. Energy is normalized within each playlist.
- Previewing/sorting and writing to Spotify are separate operations. Preserve the URI-completeness guard before the first playlist replacement; Spotify writes use batches of at most 100 tracks.
- App modules use sibling imports such as `from constants import ...`; run via the Streamlit entrypoint or include `app` in `PYTHONPATH` for direct Python checks.
- For runtime/build dependencies and deployment differences, read `mem:tech_stack`.
- For development entrypoints and commands that modify files, read `mem:suggested_commands`.
- For typing, style, and stale editor guidance, read `mem:conventions`.
- Before completing a change, use the checks in `mem:task_completion`.
- Before changing these memories, follow `mem:memory_maintenance`.
