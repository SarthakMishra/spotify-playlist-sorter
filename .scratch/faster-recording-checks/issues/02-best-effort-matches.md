# Use the best eligible recording and retry failed audio downloads

Status: resolved
Type: task

The owner inspected Pump Mix (130 entries) and requests best-effort selection instead of refusing several plausible recordings, plus retries for failed yt-dlp downloads. Cookies remain optional. This explicitly supersedes the universal upload-only score-margin rule.

Observed through the existing browser session: zero ready, 35 several-possible-recording labels, 66 no-match labels, 29 download failures. Diagnose real title/artist and download failures, preserve obvious wrong-song/version exclusions and playlist occurrences, add bounded fresh-source retries, verify offline contracts, and retry checking the actual playlist. Do not save/reorder Spotify as part of this task.


## Answer

Resolved after retrying the actual playlist. The final open job has **130/130 successfully analyzed songs and zero kept in place**, compared with 0/130 before. The last pass reused 108 cached results and resolved all 22 remaining misses. The loaded song-ID sequence is unchanged; no Spotify save/reorder occurred. Cookie mode remained anonymous.

Removed tie rejection; recognized titles inside upload decoration; accepted any relevant artist credit and strong verified-channel matches with missing credits; allowed modest duration differences bounded by 8%/20 seconds. Kept explicit wrong-artist and conflicting-version exclusions. Both source inspection and download now use audio-only formats. Failed downloads retry once with fresh extraction/media URLs and recording validation, then move to the next eligible candidate. Persistent access errors and retry counts remain bounded.

[Live evidence, reasoning and limitations](../../../docs/ytdlp-reliability-research.md#live-playlist-correction-best-effort-matching-and-download-retries) document the actual search and 403 reproductions, policy changes, before/after job snapshots and the difference between successful analysis and proven identity. `task check` passes 44 offline tests and all other required checks; `git diff --check` passes. The live page displays all 130 songs ready.
