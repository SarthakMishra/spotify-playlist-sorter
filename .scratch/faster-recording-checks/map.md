# Faster recording checks

## Notes

The owner prioritizes this reported pipeline problem over the listening pilot. Implementation choices are delegated. The existing playlist occurrence and save safeguards remain applicable.

## Decisions-so-far

- Diagnose candidate rejection and source requests separately from audio measurements.
- Cookies address YouTube access, not proof that a recording matches.

- Resolved the two deterministic reproductions with bounded flat search, reusable full metadata and structured recording evidence. Added optional session uploads/server-browser cookies, explicit anonymous mode, packaged JavaScript support and actionable source failures. [Research and validation](../../docs/ytdlp-reliability-research.md#implemented-result-and-validation).

## Fog

Direct browser-cookie access depends on Chrome's profile being available on the app server. The owner emphasized that cookies must remain optional. Both local server-browser setup and session uploads are supported, with anonymous checking when no cookies are provided. The owner supplied the open Pump Mix session. Its first observed run had zero usable analyses across 130 entries: 35 tie rejections, 66 no matches, and 29 download failures. The owner explicitly authorizes best-effort source selection and retrying failed downloads.

## Work

[01 Pipeline and YouTube access](issues/01-pipeline-and-youtube-access.md) is resolved. Forty offline tests, repository checks, browser checks and an offline Docker runtime check pass.

[02 Best-effort matches](issues/02-best-effort-matches.md) is resolved. Actual anonymous YouTube probes reproduced an overstrict title filter and HTTP 403 downloads; audio-only/fresh extraction succeeded. Live retries raised usable analysis from 0/130 to 130/130, with no kept entries; the final pass reused 108 cached results. Forty-four offline tests and repository checks pass. No Spotify reorder is part of this task.
