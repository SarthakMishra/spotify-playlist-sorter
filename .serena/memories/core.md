# Project map

- `api/app.py` owns the FastAPI routes, opaque browser sessions, OAuth state and CSRF checks, one session-owned playlist job, and static SPA serving. `api/spotify_auth.py` keeps credentials and Spotipy token caches on the server.
- `api/playlist_sorter.py` owns Spotify pagination, YouTube matching, audio analysis, transition scoring, ordering, and positional playlist writes. Analysis callbacks do not import UI code.
- Preview and save remain separate. Save requests carry the preview revision; Spotify writes check the playlist snapshot and reorder existing occurrences. Preserve duplicate and unanalyzed items. A failed partial reorder requires fresh analysis before another save.
- One Uvicorn worker and one active analysis are deliberate limits: sessions/jobs are in memory and the analysis cache is a shared JSON file. A shared session store and durable queue are required before replicas.
- Python imports use `api.*` from the repository root. Frontend routes and requests live in `frontend/src`; the browser talks to relative `/api` paths.
- For deployment and tooling constraints, read `mem:tech_stack`. For commands, read `mem:suggested_commands`. For typing and style, read `mem:conventions`. For required verification, read `mem:task_completion`. Before editing memories, read `mem:memory_maintenance`.
