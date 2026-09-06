# Better playlist arrangements

Status: needs-triage
Type: spec
Date: 2026-09-06

Make a playlist someone already likes more enjoyable to hear in order. Preserve their songs, improve the transitions and pacing, and let them understand and reverse the result.

This is an implementation plan, not a description of shipped behavior. The proposed first audience is the owner and a few invited listeners. The proposed first use is everyday listening. Those two product questions were asked during planning and remain open; the defaults below allow a concrete plan without asking the owner to make engineering decisions.

Implementation progress on 2026-09-06: ticket 01 completed its research with an offline-only outcome. Ticket 02 implemented complete entry previews, stable duplicate identities and fixed-position preservation through save. Ticket 03 added conservative matching, full-recording librosa measurements, uncertainty evidence and versioned cache checkpoints. Ticket 04 implemented Smooth/More variety, the directed objective and bounded search, optional absolute endpoint pins, and basic controls with unchanged-result handling. Ticket 05 added metadata/progress during analysis, factual coverage, bounded listening notes and elapsed-time comparison with text alternatives. Ticket 06 added complete snapshot-consistent save/readback and one-level session restore, including stale-edit and interrupted-write handling. Live integration and listening preference remain unverified.

## Product promise

"Keep your songs. Find an order that flows better."

Success means the listener prefers the arrangement after listening. A lower calculated cost is useful engineering evidence, but does not establish musical quality. The product arranges a fixed set of entries. It cannot make an unsuitable collection suitable for focus or a workout just by moving songs, and it does not promise DJ mixing, mood understanding, or discovery.

Use the terms in [CONTEXT.md](../../CONTEXT.md). In particular, a playlist entry is one occurrence, while a recording is the audio that may be shared by several entries.

## Starting point before implementation

| Existing behavior | Keep or change |
| --- | --- |
| Connect Spotify, select an editable playlist, automatically check songs | Keep the flow and server-side credentials |
| Preview, then explicitly save by moving existing items | Keep the separation and preservation safeguards |
| Unchecked items stay in Spotify but disappear from the preview | Fix first; preview and saved order must agree |
| Duplicates survive saving but the sorter groups them by track ID | Arrange individual entries; duplicates need not be adjacent |
| A YouTube result is selected without a minimum acceptance threshold | Reject doubtful matches and expose the reason |
| Custom NumPy analysis uses only the first 30 seconds | Replace the fragile extraction routines with librosa and retain endings |
| A greedy score gives key compatibility 50% of its weight | Compare actual boundaries and account for recent repetition |
| One mandatory starting song and one suggested order | Make the start optional; offer Smooth and More variety |
| Percentage match scores and an RMS-based energy chart | Explain estimated changes without claiming percentages of musical quality |
| Snapshot, revision, session and interrupted-save checks | Preserve and extend them to every new control |

The relevant code is [playlist_sorter.py](../../api/playlist_sorter.py), [app.py](../../api/app.py), [playlist-page.tsx](../../frontend/src/components/playlist-page.tsx), and [song-details.tsx](../../frontend/src/components/song-details.tsx). The existing browser regression in [test_api.py](../../tests/test_api.py) demonstrates that the preview can omit intervening fixed entries.

Repository investigation also found two extraction errors. The custom chroma routine maps a 440 Hz tone to pitch-class zero even though key detection expects A at nine. Resampling after truncation scales amplitude using the original file length. Both were reproduced with generated audio during investigation. Replacing these routines requires regression checks and invalidating existing feature caches; old estimates must not silently survive the upgrade.

## First usable release

### Open a playlist

Show the complete original list immediately after metadata loads, including duplicates, local files and unavailable placeholders. Continue the existing automatic analysis in the background. Distinguish finding recordings from measuring audio. Show completed entries and reused analyses; do not label completion as successful coverage or invent a time estimate.

Every entry has a readable state: Ready, Checking, Recording uncertain, Couldn't analyze, or Kept in place. Retain the reason behind Kept in place. A failed match is a local problem for that entry, not a reason to lose the playlist. Navigating away and returning recovers the current job within the existing session lifetime.

### Choose the feel

| Control | Behavior |
| --- | --- |
| Smooth, selected by default | Favor comfortable boundaries while discouraging short runs of the same artist or texture |
| More variety | Give artist spacing and changes in texture more influence, while retaining a transition cost |
| First song, optional | Pin a specific entry at the beginning; default is Choose for me |
| Last song, optional | Pin a specific entry at the end; default is Choose for me |

These are two arrangements of the same playlist. No sliders for algorithm weights. No required knowledge of keys or BPM. Repeated songs appear as separately labeled occurrences in pin choices. If the two profiles produce the same order, show one result and say so.

Fixed entries retain absolute positions. If a fixed item occupies the first or last slot, that slot cannot also accept another pinned entry. Explain the conflict at the control. Reject conflicting pins on the server as well. With fewer than two movable entries, show the original order and explain that there is not enough material to rearrange.

### Review what will change

Reuse the current tabs for Suggested order, Original order, and Details. Both lists include every entry at its actual position. On narrow screens, switch between lists rather than compressing two tables side by side.

Above the suggested list, show a short factual summary such as "42 songs can move. 3 stay in place." The numbers are examples, not target results. List why fixed entries stayed. Highlight at most three transitions worth checking, with evidence-based language such as "Quieter ending followed by a stronger opening" or "These artists appear close together." Unknown measurements say "Transition not assessed."

Details compare original and suggested intensity over elapsed listening time. Label the value Estimated intensity, explain that it uses audio measurements, and provide the same information in text. Leave gaps for unavailable measurements. If an entry lacks duration, omit the time chart and retain the numbered list; do not invent its duration. Technical key and tempo values remain secondary.

Do not show "87% better," "perfect transition," or a universal playlist score. A cached result is not proof of a correct recording. Recording evidence belongs in an expandable details row, subject to the integration decision below. An ordinary listener should not need to inspect it to continue.

Changing profile, pins, or an analysis invalidates the active preview. Save remains unavailable until the new arrangement is ready. Choosing the original order is always possible. If the original already wins the selected objective, say "Your current order already fits this setting" and offer no unnecessary save.

### Save and listen

Keep the existing explicit Save to Spotify action and editable-playlist restriction. Save only the exact complete arrangement associated with the preview revision and current source snapshot. Read back the playlist after the move sequence before confirming success.

After success, show Open in Spotify and Restore previous order. Restore covers the most recent successful save in this session only. It checks that Spotify still matches the saved result and uses the same move-only writer. Another edit, a server restart, session expiry, or a new playlist analysis invalidates this restore option. State that limit alongside the action; this is not a permanent version history.

A timeout or interruption after a move may have changed Spotify. Stop, clear eligibility for another save or restore, and ask the listener to reload the actual playlist. Never automatically replay an ambiguous move or promise an all-or-nothing save.

Playback stays in Spotify for this release. The app does not control shuffle, Smart Shuffle, crossfade, or Automix. Listening instructions ask testers to play in order and record playback settings because reordering alone cannot enforce the heard sequence. No embedded player is required to ship this plan.

## Recording and analysis contract

### Match the recording before trusting measurements

Retain the existing yt-dlp search/download flow only for sources and integrations whose use is established. Split candidate selection from downloading so it can be tested with metadata fixtures. Keep original title/version information alongside the cleaned search query.

Evaluate up to the existing ten search results. Check title, credited artists, duration and version qualifiers separately. A live/studio, remix/original, karaoke/original, or radio/extended mismatch is a rejection, not a small ranking penalty. Remove the current karaoke preference and view-count tie-break. A single search result must meet the same checks as ten results.

Initial conservative matching rules, to calibrate on the pilot set:

- Require artist evidence and a known duration. Accept a duration difference no greater than the larger of 3 seconds and 2% of the playlist duration.
- Search lightweight metadata and inspect at most three promising videos. Use title similarity, any matching artist credit, duration closeness and available album metadata to rank candidates. Require a score of at least 0.75, then choose the best eligible upload without a runner-up margin. Extra artist/producer credits are supporting evidence rather than mandatory. When artist fields are absent, verified-channel uploads with strong title and duration agreement can be used on a best-effort basis. Retain conflicting explicit artist/version exclusions. Allow modest duration differences within max(3 seconds, min(20 seconds, 8% of requested duration)). The owner explicitly requested best-effort selection after the real 130-entry playlist produced no usable analyses. [Follow-up and evidence](../faster-recording-checks/issues/02-best-effort-matches.md). These are heuristic rules, not probabilities.
- If no candidate clears the rules, retain the entry in place and distinguish missing metadata and no eligible recording. Show source-access failures separately. On download failure, retry that source once using fresh audio extraction and media URLs, revalidating refreshed recording metadata. If it still fails, try the next eligible candidate. Inspect at most three candidates; do not retry shared sign-in, cookie, player or rate-limit failures across the queued playlist.
- Persist the source identifier, source title and duration, matching evidence, resolver version and analysis version with the feature record. Source details do not prove permission or exact acoustic identity.

The first release offers Retry analysis and Keep in place for uncertain recordings. A full source search/picker is deferred until the pilot shows that conservative matching makes too many playlists unusable. Lowering acceptance thresholds is not the default remedy for missing coverage.

### Analyze the actual beginning, middle and ending

Add a Python-3.13-compatible librosa release to the lockfile after checking dependency compatibility. Use its loading/resampling, onset, tempo, RMS, spectral and chroma functions instead of maintaining the current replacements. [Librosa documents these feature families](https://librosa.org/doc/0.11.0/feature.html); [its repository](https://github.com/librosa/librosa) is the upstream implementation reference. yt-dlp remains the downloader, not the analyzer. [yt-dlp documentation](https://github.com/yt-dlp/yt-dlp).

Decode each accepted recording once into a 22,050 Hz mono buffer. The implemented loader uses librosa's streaming resampler with nonoverlapping five-second decode blocks to bound native-rate stereo memory. Keep 5-second feature summaries over the recording, plus the first and final 15 seconds and the remaining body. Short recordings use shorter available windows with reduced support; never fabricate a missing body or ending. Bound the pilot to recordings no longer than 20 minutes, marking longer items fixed until long-form listening is explicitly supported. Preserve genuine leading/trailing silence and fades; an active-audio subwindow can support rhythm estimates without erasing the playback boundary.

Retain segment-level RMS in log units, onset activity, tempo candidates, spectral centroid/contrast, and normalized chroma, with validity and evidence strength per measurement. Use tempo ambiguity and tonal ambiguity to reduce their influence. Silence, speech, or weak periodicity must not turn into a confident 120 BPM estimate. Key labels are optional; missing key alone must not discard an otherwise usable entry.

Estimated intensity initially combines normalized log RMS and onset activity at 0.6 and 0.4. This is a testable proxy. It does not measure emotional energy, vocal distraction, perceived loudness after Spotify processing, genre or lyrics. Changing the proxy must change the analysis/scoring version and regenerate dependent previews.

Reuse the JSON cache and existing single-process analysis lock. Version the schema, record source/metadata identity and extraction settings, deduplicate work by recording, and keep occurrence counts separate from unique-recording counts. Invalidate the unversioned cache. Write checkpoints every ten successful analyses and at clean job completion using a temporary file and atomic replacement. Limit concurrent full-recording work to two initially to avoid multiplying memory use. Remove temporary audio when each task finishes. No queue service or new database is needed for the invited pilot.

## Arrangement contract

### One complete order throughout the product

At playlist load, assign each entry an identity scoped to the source snapshot and original position. Carry that identity unchanged through candidate generation, pins, preview, scoring and save. Store the Spotify URI/ID separately; unavailable entries may have no URI. A recording's features can be shared without merging its occurrences.

The arrangement must be a permutation of all loaded entry identities, preserve fixed positions, and satisfy pins. Validate those properties before returning a preview and before saving. Generate explanations only between neighbors in that complete sequence. Unknown fixed entries still occupy listening time and break adjacency.

### A bounded objective with explicit starting values

Minimize `J = alpha * mean(T) + beta * G + gamma * R + delta * M`. Every term is in the range 0 to 1. Means and bounded penalties prevent playlist length from silently changing relative weights. All initial numbers below are engineering defaults for listening tests, not established musical laws.

| Term | First implementation |
| --- | --- |
| T, directed transition cost | Compare A's final segment with B's opening. Start with weights 0.30 tempo, 0.30 intensity change, 0.30 spectral texture distance, 0.10 chroma distance |
| G, progression cost | Disabled in the first release. Later, mean squared distance from a profile's time-based target intensity |
| R, artist repetition | For each entry, take the largest `1 / d` for an overlapping credited artist among the previous three entries, where d is position distance; use zero if none. Average over the full sequence. Preserve all credited artist IDs where available |
| M, monotony | For each window of five entries, average adjacent body-feature distances in tempo, intensity and texture. Penalize distance below 0.15 using `max(0, 1 - distance / 0.15)`, then average windows. Fewer than five entries gives zero |

| Profile | alpha | beta | gamma | delta |
| --- | --- | --- | --- | --- |
| Smooth | 0.80 | 0 | 0.15 | 0.05 |
| More variety | 0.60 | 0 | 0.25 | 0.15 |

Normalize numeric features using the loaded playlist's trusted measurements, with fixed 5th/95th percentile bounds shared by all candidates. Clip to 0..1; a zero spread contributes zero distance and a neutral intensity of 0.5. Keep raw measures for explanations. Use cosine distance for normalized chroma and a bounded mean absolute distance for normalized texture components. Tempo distance uses the minimum absolute log2 ratio over half, same and double tempo, clipped to 0..1; unreliable tempo receives less influence.

For each component, blend its distance with neutral cost 0.5 using the weaker endpoint's evidence strength. A missing measurement has zero evidence strength, not a distance of zero. Entirely unassessed edges carry a fixed neutral cost, remain in the full sequence, and display no improvement claim. Apply the same missing-data treatment within monotony windows. Report measured-edge counts separately. Do not improve a displayed score by silently excluding harder edges from one arrangement.

There is no constant per-song quality term: its sum cannot improve when every entry is retained. Harmonic weight stays small because this release evaluates consecutive playback and does not mix tracks.

### Generate candidates without a solver service

Build a directed pair-cost matrix once per analysis/scoring version. Include the original order when it satisfies pins; otherwise include a minimally moved, feasible original as a baseline. Add greedy candidates from up to four deterministic starting entries spread across the available intensity range, respecting pins and fixed slots. Expand entries independently, never group by recording ID.

Select the best feasible seed, then improve it through single-entry relocations in both directions and swaps. Recompute all affected directed edges, artist windows and monotony windows; a reversal shortcut that assumes symmetric costs is invalid. Allow at most two improvement passes and a shared budget of 5,000 candidate evaluations per profile, including the baseline and greedy seeds. Use stable iteration and original-position tie-breaks for reproducibility. Keep the best feasible candidate seen, and keep the baseline on equal cost. Do not label an unfinished search globally optimal.

For fixed entries, fill only movable positions and score the complete resulting sequence, including boundaries to fixed neighbors. Both profiles reuse analysis and pair costs. Return one preview at a time using the existing job/revision flow; switching a profile does not download the audio again.

Warm arrangement targets are under 2 seconds for 100 entries and under 5 seconds for 500 on the developer's machine, excluding downloads. Measure them before release. These are targets, not current performance claims. If the budget is too slow, reduce evaluated moves or update local costs before adding dependencies. Preserve larger existing playlists: use the feasible baseline with an explicit limited-search message if a resource guard prevents arranging them; never truncate a playlist.

## Implementation boundaries

Keep FastAPI, React, current shadcn controls, Recharts, sessions, and the move-only Spotify writer. Keep scoring helpers independent of network calls so generated features can exercise them offline, initially within `api/playlist_sorter.py`. Do not create a provider framework or rewrite the app to obtain that separation.

Extend `Track` into a complete entry representation with nullable measurements, item kind, original position, duration, fixed reason and recording status. Extend `SortRequest` with a validated profile enum and optional first/last occurrence identifiers. Update `JobView` to expose the complete original and suggested sequence, analysis coverage and only the explanations needed by the UI. Keep the saved arrangement and its revision on the server. Reject unknown profiles, foreign occurrence IDs and conflicting pins.

Replace the ID-list-only contract across `sort_playlist`, `compare_playlists`, `get_transition_analysis` and `update_spotify_playlist` together. Reuse the existing original-position move algorithm. Keep CSRF, editability, stale revision, session isolation and snapshot checks. New result and restore states need no new authentication provider or analytics service.

## Spotify and source feasibility

Ticket 01 completed on 2026-09-06 with an offline-only outcome. The [research report](../../docs/audio-source-feasibility.md) verifies the installed SDK's current endpoint/field behavior with mocked transport, so no endpoint migration is needed. Real account access and source/use permission remain unverified. The research ticket's resolved status does not clear the live-pilot requirement below. [Ticket 08](issues/08-spotify-quota-feedback.md) addresses the observed quota-error explanation gap.

The integrated product needs a concrete source/access decision before a live pilot. Spotify's current policy restricts analysis of Spotify Content, integration with another service's content, and mixing. My inference is that the existing Spotify-to-YouTube workflow cannot be assumed permitted just because the downloader works; separating code or labeling it personal use does not settle that question. [Spotify Developer Policy](https://developer.spotify.com/policy).

The feasibility ticket must record the supported use and audio source, with evidence of applicable permission. If that cannot be established, continue the analysis/arrangement work using independently supplied authorized recordings and generated fixtures, and leave the Spotify-connected audio workflow unshipped. Do not turn an export boundary into a claim of policy compliance. No user-upload product needs building just to run the offline experiment.

For development-mode apps, the current guide requires an app-owner Premium subscription, limits new apps to five users, and changes playlist endpoints/response fields to `items`. Owned and collaborative playlists are the relevant scope. Audit the installed Spotipy calls against the configured app mode rather than assuming method names prove compatibility. [Spotify migration guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide). The newer July changes make development-mode quota accounting per developer account. [July changelog](https://developer.spotify.com/documentation/web-api/references/changes/july-2026).

Saving should continue to send range moves with snapshots. The API distinguishes this from replacement, which overwrites contents. [Update Playlist Items](https://developer.spotify.com/documentation/web-api/reference/reorder-or-replace-playlists-items). No live writes were performed during planning.

## Delivery order and acceptance

| Ticket | Deliverable | Depends on | Done when |
| --- | --- | --- | --- |
| [01](issues/01-source-and-spotify-feasibility.md) | Establish source use and check current Spotify compatibility | None | Supported live path or explicit offline-only result is recorded |
| [02](issues/02-complete-entry-preview.md) | Complete entries in preview and save | None | Preview equals final order with duplicate, local and unavailable entries |
| [03](issues/03-recording-analysis.md) | Conservative matching, librosa segments, versioned cache | None for offline work | Wrong-version fixtures fail matching; generated audio verifies segment and pitch/amplitude correctness |
| [04](issues/04-arrangement-objective.md) | Smooth and More variety with optional pins | 02, 03 | Deterministic valid orders, no worse objective than feasible baseline, measured runtime |
| [05](issues/05-listener-review.md) | Review controls, honest explanations and elapsed-time comparison | 04 | A listener can choose, compare and recognize uncertainty without musical terminology |
| [06](issues/06-save-and-restore.md) | Verified save and one-level session restore | 02 | Readback and stale/partial-failure regressions pass; restore cannot overwrite later edits |
| [07](issues/07-listening-pilot.md) | Listening evidence and next-release decision | 04, 05, 06; live use requires 01 | Original, shuffle, BPM and proposed orders are compared, with ties and failures reported |
| [08](issues/08-spotify-quota-feedback.md) | Explain rate limits and exhausted quota | None | Mocked 429 responses produce useful explanations without unsafe retries or lost partial-save warnings |

Tickets describe implementation work, not authorization to deploy, contact listeners, or mutate a real Spotify playlist during this planning task. Technical implementation is delegated by the owner. Only product questions should return to the owner when a default would change the intended listening experience.

### Checks that matter

Use the repository's existing unittest framework and mocked I/O. Add a compact table-driven audio/ordering regression file rather than a new testing framework. Cover the actual failure modes:

- Full-order equality through HTTP preview and mocked save, including `[B, unchecked, A, unavailable, A]`; every occurrence survives and unavailable neighbors receive no invented transition score.
- Pitch-class mapping, resampling amplitude, distinct intros/outros, short/silent audio and ambiguous tempo using generated audio. No downloaded music in the test suite.
- Hard variant rejection, unscored single-result rejection, best-effort tie selection, missing metadata and stale cache versions using metadata fixtures.
- Directional cost, half/double tempo, neutral missing-data treatment, duplicate spacing when feasible, conflicting pins, fixed endpoints and deterministic candidate selection. Same-artist-only playlists must remain feasible.
- A 10-minute track and a 2-minute track contribute their actual duration to display/progression. Missing duration is explicit. Original and suggested comparisons use identical normalization and coverage rules.
- Stale preview, session isolation, lost Spotify responses, failure after a successful move, failed readback and refusal to restore after an external edit. No replacement call is permitted.

Run `task check` and `git diff --check` before implementation review. Manually check keyboard use, visible focus, light/dark themes, reduced motion and narrow viewports. No frontend test runner or motion redesign is required.

### Listening pilot

Begin with the owner. Add invited listeners only after the owner arranges participation; this plan does not send invitations. Use five representative playlists of 20 to 100 entries, including at least one mixed-style collection, a repetitive collection, and one with uncertain/fixed entries. Validate selected recording identities by listening before evaluating order quality.

For each playlist, compare original, seeded shuffle, basic BPM sort and both profiles under the same fixed-entry and pin constraints. Prepare label-blinded, counterbalanced comparisons from authorized audio outside the Spotify app where that use is established. Do not use Spotify audio clips as an analysis corpus or build an in-app mixed preview player.

Include randomly selected transitions and 10 to 15 minute continuous sequences; do not choose only transitions where the objective predicts a win. Ask which order the listener prefers, allow a tie/neither, and note jarring boundaries, boredom and wrong-recording discoveries. Report preferences per listener and playlist, alongside assessed-edge coverage, elapsed wait and save outcomes. Saving a suggestion is not proof of listening preference.

The proposed small-pilot decision is to proceed only if the owner prefers the suggestion to the original in at least three of five playlist sessions, no preservation failures occur, and the result shows a useful reason to beat basic BPM ordering. This is a directional product gate, not statistical validation or a market claim. If it fails, adjust matching, features or weights before adding modes. If More variety adds no perceived value, remove the extra choice.

## Later releases, driven by the listening result

| Addition | Trigger and bounded implementation |
| --- | --- |
| Journey | Listener wants a deliberate arc. Use a fixed piecewise-linear intensity target at elapsed-time fractions `[0, .2, .7, 1]` with relative intensities `[.35, .55, .85, .30]`; start weights at T .55, G .25, R .15, M .05. Evaluate G at cumulative-duration midpoints and disable this profile if duration is missing. Values need listening calibration |
| Keep songs together | Listener identifies sequences the sorter breaks. Treat an ordered, contiguous group of entries as one movable block, score all real edges, and reject conflicts with pins/fixed slots |
| Focus | Listener requests fewer disruptions. Start with steadier measured intensity; do not promise instrumental or distraction-free music without appropriate vocal/lyrical evidence |
| Workout | Listener supplies a warm-up/effort/recovery/cooldown schedule in minutes. Optimize boundaries against elapsed time; report when available tracks cannot meet it. No target heart-rate claims |
| Party | Listener wants builds with breathers and can mark familiar anchors. Do not invent familiarity from the waveform |
| Manual source correction | Conservative matching limits usefulness. Add a narrowly scoped correction flow consistent with the approved audio source; changes invalidate dependent analyses/previews |
| Manual reordering | Listeners repeatedly want local corrections after changing pins/profile. Add accessible move controls before a drag-and-drop dependency |
| Durable history or public service | Pilot proves value and users need recovery beyond the current session or broader access. Then establish public Spotify access, persistent jobs/history and operational limits |

Keep machine learning, recommendations for new tracks, lyric/mood classification, custom profile designers, automatic recurring saves and public sharing outside this release. They do not repair the current preview, matching or ordering problems.

## Comments

2026-09-06: The owner requested an implementable improvement plan and product/design questions only when necessary. Asked whether the first experience is everyday listening, a musical journey, or an activity, and whether the first audience is invited users or the public. Pending answers are recorded in [map.md](map.md). No application code was changed as part of planning.
