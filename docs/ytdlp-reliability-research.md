# Faster, more reliable recording checks

Researched on 2026-09-06 against yt-dlp's official documentation and the installed `2026.08.19` source. No personal browser profiles, cookies, live recordings or Spotify account data were accessed. The performance and matching changes below are engineering recommendations; their effect on this listener's collection still needs measurement.

The first changes should reduce unnecessary video requests, distinguish source failures from ambiguous recordings, and use the structured music metadata yt-dlp already extracts. Browser cookies should be an optional recovery path with clear setup and failure messages.

## What the current application does

At the start of this investigation, `_analyze_track` in [playlist_sorter.py](../api/playlist_sorter.py) searched ten results with full extraction enabled. It then extracted the selected video again to download it. `download=False` prevented media downloading but did not prevent extraction of every search result. Search errors were ignored and warnings hidden, so a failed extraction could eventually produce the same "Recording uncertain" result as an actual metadata ambiguity.

The matcher also demanded a 0.10 gap between the two highest scores. Two uploads with equally strong title, artist and duration evidence therefore both became unusable. It compared every artist name literally and treated uploader text as interchangeable with structured artist metadata. The cache retained only successful analyses. Rechecking unsuccessful songs repeated their source work.

These are direct code observations. They explain plausible failure mechanisms, but do not establish which mechanism caused any particular label in the user's playlist.

## Reduce requests before adding workers

Use `extract_flat="in_playlist"` for the search. The Python API defaults to resolving all URL entries; flat extraction skips those child extractions. Hydrate only a bounded shortlist. Keep the full accepted info dictionary in memory and pass it to `process_ie_result(info, download=True)` to download without another watch-page extraction. Use a downloader with downloads enabled, and do not carry a search-only `skip_download=True` option into this step. Keep expiring format URLs out of the persistent analysis cache. [YoutubeDL API and processing implementation](https://github.com/yt-dlp/yt-dlp/blob/2026.08.19/yt_dlp/YoutubeDL.py).

A flat YouTube search normally supplies video ID, title, duration, channel identity, live status and verification evidence. It does not supply the complete music description and structured music fields. Therefore preliminary filtering must tolerate missing structured metadata and recheck the hydrated result before accepting it. Reject known duration/version conflicts early; retain a small number of plausible candidates with incomplete evidence for hydration. [YouTube search-result extraction](https://github.com/yt-dlp/yt-dlp/blob/2026.08.19/yt_dlp/extractor/youtube/_tab.py).

For the app, cap full candidate extractions and keep the existing two workers initially. One search plus three candidate extractions uses fewer watch/player requests than ten candidate extractions plus a repeated selected extraction. This is a request-count expectation, not a measured speed multiplier. A shortlist can miss a correct low-ranked result; record that outcome honestly rather than accepting a weak match to fill coverage.

An offline check against the installed package passed a full video info dictionary with one audio format into `process_ie_result`, patched `extract_info` to fail on any call, and replaced the terminal `process_info` download with a mock. The result made zero extraction calls and one download-processing call with `skip_download=False`. This verifies reuse of already hydrated info without a live download.

## Use stronger recording evidence

The full YouTube extractor parses `track`, `artists`, `album`, `release_year` and `release_date` from supported auto-generated music descriptions. It also reads Song/Artist/Album metadata rows and avoids assigning those rows when the page identifies multiple songs. `channel_is_verified` is separate channel evidence. These fields can be absent. [YouTube video metadata extraction](https://github.com/yt-dlp/yt-dlp/blob/2026.08.19/yt_dlp/extractor/youtube/_video.py).

Prefer structured track and artist comparisons over decorated upload titles. Preserve version distinctions such as live, remix, acoustic, remaster and radio edit. Treat album/year as supporting evidence because the same recording can appear on several releases. A verified channel or a `- Topic` suffix alone cannot prove recording identity. Description text also remains metadata, not an audio fingerprint.

A narrowly defined acceptance path for matching structured music metadata can prevent duplicate plausible uploads from automatically failing the runner-up rule. Require independently strong title, artists, duration and version agreement, and retain uncertainty when those fields conflict. Keep the conservative margin for weaker upload-only evidence. Record this as a change to the original [matching specification](../.scratch/better-arrangements/spec.md) and [ticket 03 research](librosa-analysis-research.md), which currently require the margin for every match.

Separate "No matching recording", "Several possible recordings", "YouTube needs sign-in", "YouTube is limiting requests" and download/decoder failure. Cookies should never make a weak identity match pass.

## Enable the installed JavaScript runtime

Current YouTube support requires challenge scripts plus a supported JavaScript runtime. Node is supported from version 22 but must be enabled explicitly; Deno is the runtime enabled by default. This repository already requires Node 24. Install `yt-dlp[default]` to obtain the compatible `yt-dlp-ejs` package and keep the two packages updated together. Prefer the packaged scripts to fetching executable components during a playlist check. [Official EJS setup guide](https://github.com/yt-dlp/yt-dlp/wiki/EJS).

For Python, enable the existing runtime with `js_runtimes={"node": {}}`. The runtime must also exist in the backend's production environment, including the final Docker image, not only during the frontend build. [Python runtime options](https://github.com/yt-dlp/yt-dlp/blob/2026.08.19/yt_dlp/YoutubeDL.py).

## Offer browser cookies and a file alternative

The Python tuple is `(browser, profile, keyring, container)`. For example, `("chrome", "Default", None, None)`. Browser names are lowercase and explicitly selected Python keyrings use uppercase names such as `GNOMEKEYRING` or `KWALLET6`. The profile can be a name or path. Container selection is Firefox-specific. Browser extraction copies the cookie database into temporary storage and may skip cookies it cannot decrypt while returning a partial jar. Missing profiles, unavailable keyrings and partial decryption therefore need distinct feedback. [Cookie loading and browser extraction](https://github.com/yt-dlp/yt-dlp/blob/2026.08.19/yt_dlp/cookies.py).

Browser mode reads the browser on the machine running the backend. It cannot read a remote visitor's Chrome through the web page. For local use, snapshot cookies once per checking job and give each downloader an independent in-memory copy; avoid repeatedly decrypting the browser store for every candidate. Retain only the YouTube domains needed for these requests. Keep file and browser inputs read-only and never return cookie values through an API response or log. These are application recommendations, not guarantees supplied by yt-dlp.

Keep server browser/profile selection operator-configured. A remote client must not be able to request arbitrary browser profiles or filesystem paths. For uploaded exports, bind the in-memory cookie contents to the submitting session and clear them on logout or expiry.

Chrome on Windows can deny access to its open database, and modern Chrome cookie encryption can prevent direct extraction. Offer file export when closing Chrome or selecting the correct profile does not resolve the error. Do not suggest weakening browser encryption. [Database-lock issue](https://github.com/yt-dlp/yt-dlp/issues/7271), [Windows cookie-decryption issue](https://github.com/yt-dlp/yt-dlp/issues/10927).

For Chrome file export, link to the exact [Get cookies.txt LOCALLY extension](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc). Its export supports Netscape and JSON; this app needs Netscape. The extension's current listing identifies its publisher as kairi003 and links its source code. [Extension listing](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc).

yt-dlp's FAQ recommends this extension and explicitly distinguishes it from the removed "Get cookies.txt" extension. The cookie file needs a Netscape header and tab-separated cookie records. Combining `--cookies-from-browser` with `--cookies` exports all sites' browser cookies, so the app should guide users to a YouTube-only extension export instead. [Official cookie FAQ](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp).

Suggested instructions for the app:

1. Install the linked extension and allow it in Incognito in Chrome's extension settings.
2. Open one Incognito window, sign in to YouTube, and use that same tab to open `https://www.youtube.com/robots.txt`.
3. Export only `youtube.com` cookies in Netscape format with the extension.
4. Close the Incognito window and do not reopen that session. Select the exported file in the app, or configure the existing read-only cookie file on the backend.

YouTube rotates cookies in open browser sessions; the private-window export procedure is yt-dlp's documented way to avoid continued rotation of that exported session. Cookies are optional and should be used only when needed. Account use still has limits. [Official YouTube cookie instructions](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies).

## Keep downloads bounded and failures visible

Keep audio-only `bestaudio` selection with an explicit fallback if needed; `bestaudio/best` can download video when an audio-only format is unavailable. Avoid pinning a format ID or stripping every manifest, since available formats change. Bound HTTP, extractor and fragment retries and use the existing retry-sleep options for backoff. Set `skip_unavailable_fragments=False` so incomplete audio cannot silently pass as a complete recording. Preserve yt-dlp's cache of reusable extraction data. [Options and format selection](https://github.com/yt-dlp/yt-dlp).

Set network timeouts for search and candidate extraction as well as downloading. Keep failure categories and stage timings without storing signed URLs or account data. Retry transient network errors within the bounded budget; an account challenge or rate limit should stop repeated doomed requests and explain the next action.

The YouTube extractor documentation recommends default client selection and suggests about 5–10 seconds between downloads when rate limits occur. More workers or fragment concurrency can make the problem worse. Those guidelines are approximate and should not become a promised account quota. [YouTube rate-limit guidance](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#common-youtube-errors).

If normal clients still fail because of PO-token requirements, the current documented path is an `mweb` client with a PO-token provider plugin. Manually collecting a token is no longer recommended because many tokens are video-bound. This requires a separate provider setup; cookies and JavaScript challenge scripts do not replace it. Defer that dependency until diagnostics show it is necessary. [Official PO-token guide](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide).

## Check the result

Keep offline tests for request counts, structured metadata, conflicting versions, duplicate plausible uploads, challenge failures and read-only cookies. Measure search, hydration, download and audio-analysis time separately. Compare accepted-match coverage and incorrect matches on the same listener-reviewed recording set before and after the change. A faster check or fewer uncertainty labels alone does not demonstrate better matches.


## Implemented result and validation

Implemented on 2026-09-06 in [playlist_sorter.py](../api/playlist_sorter.py), [YouTube access](../api/youtube.py) and the [setup page](../frontend/src/components/youtube-access.tsx). Cookies remain optional. With no upload or configured source, yt-dlp receives no cookie settings and continues anonymously. The owner can explicitly select anonymous access even when a server cookie source exists. The app's short explanation says cookies can help find the correct recording when YouTube requires sign-in, and are used for searches and audio downloads.

The resolver now searches ten flat results, filters known title/duration/version conflicts and fully extracts at most three promising candidates. Downloads reuse the chosen full info dictionary in memory. Structured track names retain genuine title words and artist names; credited-feature display suffixes are normalized without dropping later version qualifiers. Exact structured title, every expected artist and album agreement may pass without the upload-only margin. The 0.85 minimum score and hard duration/version checks remain; weaker candidates still need the 0.10 margin. Both the specification and the earlier librosa research now record this correction.

| Deterministic fixture | Before | After |
| --- | --- | --- |
| One matching result among ten, through yt-dlp's actual playlist processing | 10 video detail extractions | 1 video detail extraction; hard cap 3 |
| Download an already checked video | Extract selected URL again | No extraction call; existing formats processed once |
| Exact credited album upload plus an uncredited duplicate | Recording uncertain | Ready, choosing the credited match |
| Shared sign-in or rate-limit failure over 20 entries | No shared failure stop | At most 2 in-flight extraction calls, then queued work stops |
| Cookie configuration absent | Anonymous | Anonymous, explicitly tested |
| Browser cookies across multiple uncached entries | Browser mode unavailable | One read/decryption per checking job |

The first two reproduction tests were run before implementation with `uv run python -m unittest discover -s tests -p 'test_recording_pipeline.py' -v`. Both failed with the target symptoms: `Recording uncertain` for the credited album fixture and `Hydrated 10 candidates for one recording`. The expanded regression file now passes. These fixtures measure request work and expected identity decisions, not real YouTube network latency or real-world match accuracy.

A generated 180-second mono tone took **1.891 seconds** under cProfile before these changes, including about 1.3 seconds of imports. That observation supported targeting lookup requests first. The full-recording librosa measurements, section boundaries, memory limit and two-worker ceiling remain unchanged. There is no claim of a measured end-to-end speed multiplier.

The installed dependency set now includes yt-dlp 2026.08.19, compatible EJS 0.8.0 and Linux SecretStorage support. Node 24 is explicitly enabled for the backend. Retry counts/timeouts apply to search, metadata and downloads; missing fragments fail the recording instead of being silently skipped. Sign-in, cookies, rate limits, JavaScript challenges, lookup, download and measurement failures have distinct safe explanations. Stage timings and candidate counts omit cookie values, paths and signed media URLs. Successful analyses use resolver version 2, so old resolver caches rebuild once. Failed searches are not persistently cached.

Cookie exports are validated before yt-dlp can print malformed cookie lines. Only unexpired YouTube-domain cookies are retained, including valid session cookies. Each yt-dlp instance gets an independent in-memory jar. Files and browser profiles remain read-only. Uploads belong to the authenticated session; CSRF is required, busy jobs reject settings changes, and responses never contain cookies or server paths. Browser/profile selection is operator-configured; the web API cannot request an arbitrary local profile. Direct Chrome access and Chrome-extension upload are documented in the app and README. No personal browser profile was opened during validation.

Container validation exposed the existing Alpine image trying to build llvmlite/LLVM from source. The image now uses Debian slim so the locked manylinux wheels install, and includes a compatible Node binary in the backend image. uv is copied from its versioned binary image using the [official Docker integration pattern](https://docs.astral.sh/uv/guides/integration/docker/). An offline container smoke check ran as UID 10001 with network disabled and verified Node v24.20.0, EJS, anonymous configuration, generated-audio analysis, `/api/health` and the compiled SPA.

`task check` passes lint, formatting, Python/TypeScript checks, **40 offline tests** and the production build. The [new browser check](../.scratch/faster-recording-checks/check_access.cjs) passes cookie upload/removal, anonymous mode, configured-browser guidance, invalid-file feedback, keyboard navigation and axe checks at 1280px/light, 390px/dark and 320px/light. The existing arrangement/progress/save/restore browser checks also pass. [Phone screenshot](../.scratch/faster-recording-checks/dark-390-youtube-access.png).

No live recording download, Spotify mutation, personal-cookie extraction or listener-reviewed matching benchmark was performed. A real before/after check on the same authorized playlist is still needed to measure latency and false matches. The app now retains the safe timings and separates failure reasons needed for that next check.


## Live playlist correction: best-effort matching and download retries

The owner then requested inspection of the actual open Pump Mix playlist and explicitly asked to use the best available recording instead of rejecting ties. This changes the conservative matching policy described above.

The initial authenticated job had **130 entries and zero usable analyses**: 35 `Several possible recordings`, 66 `No matching recording found`, and 29 download failures. [Initial public job evidence](../.scratch/faster-recording-checks/pump-mix-before.json) contains only track metadata and outcomes, not credentials.

Anonymous live probes reproduced concrete causes:

- For `Tension`, search returned official audio `ocN2bmt4UHk` at 169 seconds against Spotify's 168.2 seconds, but the upload's extra artist/album wording defeated title filtering.
- For `Back In Black`, the existing metadata-reuse path returned HTTP 403 on `rrim6_9VSeM`. Fresh extraction of that same source downloaded 251.69 seconds successfully. Extracting audio-only metadata before reuse also downloaded successfully. Matching had been extracting with yt-dlp's default video-oriented format selection, while downloading requested audio-only formats. Both stages now request `bestaudio`.
- `Girls Like To Swing` had a verified T-Series upload at 243 seconds matching Spotify's 243.165 seconds, but no structured artist fields. `Jagga Jiteya` and `Dhaakad` had official full-audio uploads differing by about 9.5 and 11.4 seconds respectively. Strict first-credit checks and the 2% duration window excluded these plausible matches.

The implemented policy now selects the best eligible candidate without a runner-up margin, using a minimum heuristic score of 0.75. Any listed artist can supply credit evidence. Verified-channel uploads with strong title/duration agreement may pass when credits are missing; explicit conflicting artist credits still fail. Duration tolerance is max(3 seconds, min(20 seconds, 8% of requested duration)). Known conflicting version tags remain excluded. Search asks for audio and uses the first two artist credits to avoid excessively long queries. Candidate extraction remains capped at three.

A download first reuses the aligned audio metadata. On failure it waits briefly, reextracts fresh metadata/media URLs, revalidates the recording, and retries once in a clean temporary directory. If that still fails, the next eligible candidate is tried. Existing HTTP/fragment retry limits and shared access-error stops remain. Cookies are optional and the live retries used anonymous access.

The first corrected pass analyzed **108/130** entries. The second pass reused those 108 cached analyses and resolved the remaining 22. The final authenticated job reports **130/130 ready, zero kept in place, zero outstanding download failures**. All 130 rows are visible, and the loaded Spotify ID order matches the initial order. [First retry](../.scratch/faster-recording-checks/pump-mix-first-retry.json), [final result](../.scratch/faster-recording-checks/pump-mix-after.json).

`task check` passes **44 offline tests**, lint, formatting, type checks and production build. New regressions cover close-score selection, actual upload-title patterns, incomplete soundtrack credits, modest duration differences and fresh extraction after HTTP 403. `git diff --check` passes. No Spotify reorder or save was performed.

These results establish analysis coverage on this playlist. They do not establish perfect recording identity or listener preference: best-effort uploads can have different padding or edits, and that can affect measured transitions.
