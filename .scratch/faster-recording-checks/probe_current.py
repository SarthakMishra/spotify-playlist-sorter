"""Anonymous diagnostic of two owner-reported failures; no Spotify writes or cookie reads."""
import json
import re
from time import perf_counter
import yt_dlp
from app.playlist_sorter import SpotifyPlaylistSorter, _metadata, _shortlist, _rank_recordings
from app.youtube import youtube_options

for track in [
 {'id':'probe-tension','Track':'Tension','Artist':'Diljit Dosanjh','duration_ms':168200},
 {'id':'probe-back-in-black','Track':'Back In Black','Artist':'AC/DC','duration_ms':256000},
]:
 started = perf_counter()
 options = {**youtube_options(''), 'extract_flat':'in_playlist'}
 with yt_dlp.YoutubeDL(options) as ydl:
  info = ydl.extract_info(f"ytsearch10:{track['Track']} {track['Artist']}",download=False)
  entries = list(info.get('entries') or [])
  print(json.dumps({'track':track['Track'],'search_seconds':round(perf_counter()-started,2),'results':[{k:e.get(k) for k in ('id','title','duration','channel')} for e in entries]},ensure_ascii=False),flush=True)
  chosen = _shortlist(entries,_metadata(track))
  print('shortlisted',len(chosen),flush=True)
  if chosen and track['id'] == 'probe-back-in-black':
   video = ydl.extract_info('https://www.youtube.com/watch?v='+chosen[0]['id'],download=False)
   ranked = _rank_recordings([video],_metadata(track))
   print(json.dumps({'ranked':ranked},ensure_ascii=False),flush=True)
   if ranked:
    try:
     audio,sr = SpotifyPlaylistSorter._download_and_load(ranked[0],cookie_text='',video_info=video)
     print('downloaded_seconds',len(audio)/sr,flush=True)
    except Exception as error:
     cause = error.__cause__
     print('download_failure',type(error).__name__,str(error),'cause',type(cause).__name__,re.sub(r'https?://\S+','<url>',str(cause)),flush=True)
