# Audio source and Spotify feasibility

Checked 2026-09-06 for [ticket 01](../.scratch/better-arrangements/issues/01-source-and-spotify-feasibility.md).

Result: offline-only for the new arrangement experiment until the intended Spotify integration and audio-source permissions are established. Public documentation establishes available API contracts, but it does not establish permission for this app's Spotify-to-YouTube analysis workflow. No recording license or service-specific approval was supplied with this ticket. This research does not disable the existing application or claim that a live integration has passed review.

The immediate supported input is generated audio and invented metadata for engineering checks. A listening experiment can use standalone recordings supplied independently with documented permission covering local analysis and the intended listening comparisons. No such real-recording corpus has been verified yet. Keep that experiment independent of Spotify and YouTube calls, use local files without an upload UI, and do not treat a Spotify export step as a permission workaround.

Spotify's published rules and their application to this product are separate:

| Evidence | Consequence |
| --- | --- |
| Developer Policy III.5 prohibits integration with another service's streams or content; III.13 prohibits analysis of Spotify Content or the service; III.14 restricts AI/ML ingestion. III.7 restricts mixing or overlapping Spotify Content. [Policy, effective 2025-05-15](https://developer.spotify.com/policy) | Inference: replacing Spotify audio with a YouTube recording does not establish an allowed integrated workflow. Conventional signal processing avoids no applicable analysis rule merely because it uses no ML. |
| Spotify Content includes metadata, playlists and user data as well as recordings. The Developer Terms also describe a separately executed written agreement. [Developer Terms II.8 and IX.1](https://developer.spotify.com/terms) | Limiting Spotify to metadata does not by itself settle permission. Evidence must cover the actual application and intended processing. |
| Policy III.9 permits a specific exception for transferring a user's personal data or playlist metadata to another service. [Developer Policy](https://developer.spotify.com/policy) | Inference: this transfer exception alone does not establish permission for subsequent integrated analysis, or exempt personal projects from the other rules. |

For YouTube, the published terms restrict downloading and other content use to what the service authorizes or what YouTube and applicable rightsholders permit in writing. They separately restrict automated access, with stated exceptions. The permission to listen personally does not expressly authorize this downloader and analysis pipeline. [YouTube terms, Permissions and Restrictions, dated 2023-12-15](https://www.youtube.com/static?template=terms).

yt-dlp provides downloading and metadata extraction, including a source-reported `license` field. Its software availability and that metadata are not evidence that this product has the necessary service or recording permissions. That is an inference about this workflow, not an extra condition imposed by yt-dlp. [yt-dlp upstream documentation](https://github.com/yt-dlp/yt-dlp).

The external question remains: what applicable permission covers this specific Spotify metadata, recording matching, third-party audio analysis and playlist-saving workflow, and the chosen recording source? A local credential, successful OAuth login or successful HTTP request answers technical access only. No service was contacted for approval during this research.

The official quota documentation says to inspect App Status in the developer dashboard to identify development or extended quota mode. Development mode requires the owner's Premium subscription and normally allows five allowlisted users; login alone can succeed while API calls return 403 for an unlisted user. The current documentation also distinguishes request quotas from rate limits. These public rules do not establish this configured app's mode, subscription, allowlist, quota balance or actual accessible playlists. [Quota modes](https://developer.spotify.com/documentation/web-api/concepts/quota-modes).

The February migration applies to development mode, with new apps changing on February 11 and existing apps on March 9. Extended quota apps are excluded from that migration. Existing excess app/user counts were grandfathered. The guide's one-client limit has since changed, as recorded below. [February migration guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide).

| Later official change checked | Effect on this plan |
| --- | --- |
| March retains album and track `external_ids`, reversing their announced removal. [March changelog](https://developer.spotify.com/documentation/web-api/references/changes/march-2026) | Do not remove ISRC support on the mistaken assumption that the field disappeared. Missing individual values still require handling. |
| May adds immutable `account_id` to the current-user response for linking accounts. [May changelog](https://developer.spotify.com/documentation/web-api/references/changes/may-2026) | A future persistent account link should use it. It does not imply that playlist `owner.id` is an `account_id`. |
| July raises the app limit to 25 client IDs per developer. Development quota buckets are shared across the developer's apps, and quota exhaustion returns 429 with `error.reason` equal to `QUOTA_EXCEEDED`. [July changelog](https://developer.spotify.com/documentation/web-api/references/changes/july-2026) | Do not repeat the February one-client rule or describe multiple apps as separate quota allocations. |

July was the latest changelog linked from the official documentation when checked. Searches for official August and September changelogs returned no results; this is not evidence that undocumented service behavior cannot change.

These are the current published playlist contracts to compare with the locked SDK and application. They are documentation evidence, not observed live responses:

| Operation or data | Contract and required handling |
| --- | --- |
| List playlists | `GET /me/playlists` returns owned or followed playlists. Each playlist's count is `items.total`; `tracks` is deprecated. Description and owner display name can be null, images can be empty, and unavailable track objects can be null. Being listed does not establish editability. [Current-user playlists](https://developer.spotify.com/documentation/web-api/reference/get-a-list-of-current-users-playlists) |
| Read full playlist | `GET /playlists/{id}` uses `items` for its item page. It supplies contents only for the current owner's or collaborator's playlists. Treat absent contents as inaccessible, never as an empty playlist. [Get playlist](https://developer.spotify.com/documentation/web-api/reference/get-playlist) |
| Read item pages | `GET /playlists/{id}/items` has documented page size 1 to 50, default 20. Its response array is `items`, each entry's payload is `item`, and the payload type can be track or episode. Nonowners/noncollaborators receive 403. [Get playlist items](https://developer.spotify.com/documentation/web-api/reference/get-playlists-items) |
| Renamed fields | Development-mode calls migrate from `/tracks` to `/items`; parsing must also adopt the playlist-level `items` and entry-level `item` names. Removed track fields include `available_markets`, `linked_from` and `popularity`; `GET /me` no longer supplies `product`. [February migration guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide) |
| Local entries | Local recording objects can contain null IDs and sparse metadata. Preserve occurrence positions instead of requiring every entry to identify a catalog recording. [Playlist local-file documentation](https://developer.spotify.com/documentation/web-api/concepts/playlists) |
| Move entries | `PUT /playlists/{id}/items` accepts `range_start`, `insert_before`, `range_length` and `snapshot_id`; success returns the next snapshot. `uris` selects replacement and overwrites contents. Continue using range moves only. [Update playlist items](https://developer.spotify.com/documentation/web-api/reference/reorder-or-replace-playlists-items) |

The new item endpoint's response schema says `item`, while some field-filter examples on that same page still say `track`. Implement fixtures from the named current response fields and verify the exact request fields, pagination and parsed result. Do not copy the stale examples or infer compatibility from a Spotipy method named `playlist_items`. [Get playlist items](https://developer.spotify.com/documentation/web-api/reference/get-playlists-items).

## Local configuration and SDK evidence

The local `.env` and process environment were inspected through a values-withheld summary. Client ID and secret are set. There is no explicit redirect override, so the app uses its loopback callback default. The optional YouTube cookie input is unset, and no legacy `.spotify_cache` file exists. The source app keeps current tokens in server memory. No secret, token, cookie value or client identifier was printed or copied into this report. [Authentication implementation](../api/spotify_auth.py).

There is no local setting or supplied dashboard record that establishes development versus extended quota mode. Credentials alone cannot reveal it. Premium status, allowlisted users, registered dashboard callback, approved use and actual accessible playlists remain unverified. No authenticated live API request was made. The code requests playlist read/modify scopes and filters to owned or collaborative playlists, but that establishes intended scope only. [Authentication and filtering](../api/spotify_auth.py), [analysis editability check](../api/app.py).

The lockfile and installed distribution both report Spotipy 2.26.0. Inspection of the installed `spotipy/client.py` and an [offline transport probe](../.scratch/better-arrangements/check_spotify_contract.py) establish the following behavior. The probe supplies invented metadata and fake credentials, intercepts Requests transport, and rejects socket connections. It does not download audio or invoke live Spotify.

| Checked call | Observed behavior with mocked HTTP responses |
| --- | --- |
| `current_user_playlists(limit=50)` | Sends `GET /v1/me/playlists`; app reads both `items.total` and legacy `tracks.total`, tolerating empty images and null owner display name |
| `playlist_items(playlist_id)` | Sends `GET /v1/playlists/{id}/items` with limit 50; `next()` follows the returned page URL |
| `_fetch_tracks_from_spotify()` | Reads current `item` and legacy `track` payloads; missing duration/popularity and null album are tolerated; duplicate entries remain distinct in `original_items`; null, local and episode entries retain placeholder positions |
| `playlist_reorder_items(...)` | Sends `PUT /v1/playlists/{id}/items` with `range_start`, `range_length`, `insert_before` and `snapshot_id`; no replacement `uris` field is sent; the returned snapshot passes through |
| Fake quota-exhaustion response | HTTP 429 becomes `SpotifyException` carrying `QUOTA_EXCEEDED` and the supplied `Retry-After` header; the probe observes one transport call and the app factory configures zero retries |

These are exercised SDK/application contracts, not proof of real account access or live response behavior. The endpoint and field migration is already implemented for the operations this product uses. No SDK upgrade, replacement client or `/items` rewrite is needed. [Locked dependency](../uv.lock), [app parser/writer](../api/playlist_sorter.py), [existing HTTP regression](../tests/test_api.py).

One concrete response-handling follow-up remains. `spotify_error` turns non-401 Spotify exceptions, including 429, into a generic HTTP 502 retry message, while background jobs lose quota-specific explanations. The SDK preserves information the product can use. [Ticket 08](../.scratch/better-arrangements/issues/08-spotify-quota-feedback.md) specifies distinguishing a waitable rate limit from exhausted quota without automatically replaying moves. [Current error/job handling](../api/app.py), [July response contract](https://developer.spotify.com/documentation/web-api/references/changes/july-2026).

Reproduce the probe from the repository root:

```bash
PYTHONPATH=. uv run python .scratch/better-arrangements/check_spotify_contract.py
```

It passed on the installed locked version. The existing `task check` also passes; it validates application lint/types, five offline tests and the frontend production build. Neither check validates a live account or grants source permission.

## Ticket outcome

Resolve ticket 01 as research completed with an **offline-only** outcome. Resolution does not grant live-pilot eligibility. Generated-audio and invented-metadata work can proceed now; real listening comparisons need an independently supplied authorized corpus. A live integrated pilot additionally needs evidence covering the actual service/content use and account/dashboard access. Those external facts stay open in the map.

The next frontier is ticket 02, which makes the full preview match the saved sequence. The quota-feedback follow-up is separately specified; no application behavior changed in this research ticket.
