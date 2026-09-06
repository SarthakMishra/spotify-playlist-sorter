# Explain Spotify rate limits and exhausted quota without unsafe retries

Status: ready-for-agent
Type: task
Blocked by: none

Ticket 01 found that Spotipy 2.26.0 preserves the 429 reason/header, while `spotify_error` returns generic HTTP 502 and background jobs hide that distinction. See the [research evidence](../../../docs/audio-source-feasibility.md#local-configuration-and-sdk-evidence).

## Work

- Handle HTTP 429 consistently in foreground requests and analysis/sort/save jobs. Use one shared explanation where those paths need the same behavior.
- When the reason is `QUOTA_EXCEEDED`, say that Spotify's usage allowance is exhausted and the action cannot complete now. Do not invent a reset time or recommend creating another app.
- For a rate-limit response with a valid positive `Retry-After` delay, explain when to retry and preserve the delay on foreground responses. Handle a missing or invalid delay without inventing a countdown. Distinguish quota exhaustion even if that response also carries a delay.
- Preserve zero automatic retries for moves. After any interrupted save, keep the existing partial-save warning and require a fresh playlist read before another mutation. No quota message may imply that nothing changed after earlier successful moves.
- Keep status/details private to the session and avoid echoing arbitrary upstream messages. Use the current UI's error display; no new queue or retry scheduler is needed.

## Acceptance

Use a few `unittest` cases with mocked Spotify responses. Cover a plain rate limit with a 30-second delay, quota exhaustion, missing/invalid delay, and a 429 after an earlier successful playlist move. The user sees the correct explanation, a mutation is never replayed automatically, and interrupted saves remain ineligible for retry without reload.

Example upstream body:

```json
{"error":{"status":429,"message":"Too many requests","reason":"QUOTA_EXCEEDED"}}
```

Run `task check` and `git diff --check`. This ticket has no live-access dependency because mocked responses establish its behavior.

## Comments

2026-09-06: Created from ticket 01's SDK and error-path inspection. Endpoint and item-schema migration already work; this task addresses the user-visible response handling gap. [Official July change](https://developer.spotify.com/documentation/web-api/references/changes/july-2026).
