"""Change only metadata format selection, retaining the same source and download reuse."""
import re
from time import perf_counter
import yt_dlp
from app.playlist_sorter import SpotifyPlaylistSorter
from app.youtube import youtube_options
source={'id':'rrim6_9VSeM','url':'https://www.youtube.com/watch?v=rrim6_9VSeM','duration':252}
with yt_dlp.YoutubeDL({**youtube_options(''),'format':'bestaudio'}) as ydl:
 video=ydl.extract_info(source['url'],download=False)
 print('audio_metadata_format',video.get('format_id'),flush=True)
 try:
  audio,sr=SpotifyPlaylistSorter._download_and_load(source,cookie_text='',video_info=video)
  print('reused_audio_metadata_downloaded_seconds',len(audio)/sr,flush=True)
 except Exception as error:
  print('reuse_failure',str(error),'cause',re.sub(r'https?://\S+','<url>',str(error.__cause__)),flush=True)
