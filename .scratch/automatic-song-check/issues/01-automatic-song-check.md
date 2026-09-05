# Check songs when opening a playlist

Status: claimed
Type: task

Opening an unchecked playlist should immediately show Checking songs and start analysis without an extra button. Improve the loading state using the Emil Design Engineering skill, then preserve the existing sorting and saving flow.

## Comments

Keep existing jobs and previews, avoid duplicate starts, respect other active jobs, handle empty playlists, and retain an explicit retry after errors. Use the existing progress component with honest counts and reduced-motion support.
