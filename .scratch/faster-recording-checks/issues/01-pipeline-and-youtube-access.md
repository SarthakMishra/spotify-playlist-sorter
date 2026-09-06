# Improve recording matching, checking speed and YouTube cookie setup

Status: resolved
Type: task

The owner reports mostly Recording uncertain results and very slow checking. Research current yt-dlp guidance, reproduce avoidable uncertainty/work, improve the pipeline, and add browser-cookie support plus Chrome-extension export instructions in the app.

Keep exact recording/version checks, complete bounded audio measurement, read-only cookie sources and private credentials. Verify improvements with offline regressions and measured extraction/request work; do not attribute fixture results to the owner's real playlist. Capture research under docs/ and run task check plus browser checks for the setup UI.


## Answer

Implemented and verified on 2026-09-06. [Research and measured checks](../../../docs/ytdlp-reliability-research.md#implemented-result-and-validation) contain the primary sources and evidence limits.

- Reproduced the reported uncertainty pattern and excess extraction work before changing code. Flat search plus a three-candidate cap reduced the measured fixture from ten full detail extractions to one. Downloading reuses already checked formats.
- Added exact structured track/artist/album evidence, preserved featured credits and real title words, and retained strict duration/version rejection. Weaker metadata still requires the existing score margin. Revised the original matching spec to record this product correction.
- Enabled packaged EJS and Node, bounded retries across stages, required complete fragments, separated actionable failure messages, and stopped queued requests after shared access errors. Stage timings and request counts are recorded without credentials or signed URLs.
- Added optional read-only file/browser configuration, one cookie snapshot per job, and a YouTube access page with session-scoped file uploads, removal/anonymous mode, direct Chrome setup and the official extension guide. No cookies means anonymous yt-dlp requests. Cookie values never appear in responses or logs; malformed exports are rejected before the upstream parser can print them.
- Added explicit downloading progress and a way to check unmatched songs again while reusing successful current-version analyses. The old resolver cache rebuilds once.
- Included Node in the backend container and corrected the existing Alpine/llvmlite build incompatibility by using Debian slim with the locked binary wheels.

`task check` passed all lint/format/type checks, 40 offline regressions and the production build. `git diff --check` passed. [Browser checks](../check_access.cjs) passed at 1280px/light, 390px/dark and 320px/light, including keyboard navigation and axe; the existing arrangement/progress/save/restore checks also passed. The Docker image built and the [runtime smoke check](../container_smoke.py) verified anonymous setup, Node/EJS, generated audio and API/SPA serving with networking disabled as UID 10001.

The owner reiterated that cookies must remain optional and their benefit/use must be explained briefly. The screen now states that optional cookies can help find the correct recording when YouTube requires sign-in, are used for searches and audio downloads, and checking continues without them.

No personal browser profile, real-recording download or live Spotify mutation was used. Real-playlist speed and matching accuracy still require a listener-reviewed comparison; the measured request reduction is not a live speed multiplier.
