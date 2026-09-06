"""Retry an owner-selected playlist recording anonymously with fresh yt-dlp extraction."""
import re
from time import perf_counter
from app.playlist_sorter import SpotifyPlaylistSorter

source={'id':'pAgnJDJN4VA','url':'https://www.youtube.com/watch?v=pAgnJDJN4VA','duration':254}
started=perf_counter()
try:
 audio,sr=SpotifyPlaylistSorter._download_and_load(source,cookie_text='')
 print('fresh_extraction_downloaded_seconds',len(audio)/sr,'elapsed',round(perf_counter()-started,2),flush=True)
except Exception as error:
 print('fresh_failure',str(error),'cause',re.sub(r'https?://\S+','<url>',str(error.__cause__)),flush=True)
