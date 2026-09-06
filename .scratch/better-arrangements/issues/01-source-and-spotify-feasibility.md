# Establish the supported audio source and Spotify integration

Status: resolved
Type: research
Blocked by: none

Resolve the live-integration uncertainty described in the [specification](../spec.md#spotify-and-source-feasibility). Offline work on the other tickets can proceed while this question remains open.

## Work

- Check the configured app's quota mode and accessible playlist scope without printing secrets. Inspect locked Spotipy behavior against current official endpoints and response fields, including `/items`, item-level field names and nullable metadata. Method names alone are insufficient evidence.
- Record the supported audio source/use and evidence of applicable permission. Consider the actual Spotify/other-service integration, not just permission to run yt-dlp. Do not interpret local or personal use as an exemption.
- Record whether authorized standalone recordings can support the listening experiment if integrated use cannot be established. No upload UI is needed for the offline experiment.
- Document any concrete compatibility changes as a follow-up task with mocked HTTP examples. Keep this ticket read-only for the source app; do not contact Spotify, invite users, download music or reorder live playlists as part of research.

## Acceptance

Produce a dated answer with official source links, observed SDK request/response behavior, and one explicit result: supported live path with evidence, or offline-only until the stated external question is resolved. Unresolved permission must remain unresolved; a written report alone does not clear live use. Update the map and distinguish technical access from permission.

## Comments

2026-09-06: Planning checked the Spotify policy, February migration guide and July changelog. Account configuration, live endpoint behavior and source permission were not verified.

2026-09-06: Claimed as the first unresolved, unblocked frontier ticket at the owner's request. Research only; inspect local configuration without exposing secret values, exercise SDK requests with mocked transport, and record source/access evidence.

## Answer

2026-09-06: Completed with an **offline-only** outcome for the new arrangement experiment. [Dated findings and primary sources](../../../docs/audio-source-feasibility.md).

- The installed/locked Spotipy 2.26.0 already uses `/items`, valid page sizes and range-move payloads. The application parses current and legacy item fields. No endpoint migration or SDK replacement is required.
- The [runnable probe](../check_spotify_contract.py) verifies the actual SDK request transport with fake responses, including pagination, duplicate/null/local entries, move snapshots and quota exception details. No live requests, recordings or real credentials are used by the probe.
- Local client credentials are configured and the effective callback is the app's loopback default. Quota mode, Premium, allowlist, registered callback and actual account access cannot be established from those values; they remain unknown.
- No evidence establishes permission for this app's Spotify-to-YouTube analysis workflow or a real-recording evaluation corpus. Use generated audio/invented metadata for engineering now. A separate authorized standalone corpus can support listening later. Resolving this research ticket does not clear integrated live use.
- [Ticket 08](08-spotify-quota-feedback.md) specifies the observed user-visible quota/rate-limit handling gap. The SDK already retains the information required for that fix.

Validation: offline SDK probe and `task check` passed. Application source, dependencies and credentials were unchanged. The next frontier is ticket 02.
