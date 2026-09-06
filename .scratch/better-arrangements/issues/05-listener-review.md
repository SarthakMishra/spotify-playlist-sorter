# Help listeners compare and understand the arrangement

Status: resolved
Type: task
Blocked by: 04

Implement the first-release controls and review flow in the [specification](../spec.md#first-usable-release), using the existing page, tabs, shadcn controls and Recharts.

## Work

- Reuse the Smooth/More variety and optional first/last controls implemented in ticket 04. Preserve distinct occurrence labels, fixed-slot explanations and stale-save blocking while improving the review flow.
- Keep the complete list visible through loading, ready, uncertain and failed-entry states. Separate progress from successful analysis coverage and support returning to the current session job.
- Show original and suggested complete orders with factual coverage and at most three transition explanations. Show unassessed boundaries honestly. Do not turn raw cost into a musical-quality percentage.
- Use elapsed listening time for the original/suggested intensity comparison, with missing measurements shown as gaps and a text equivalent. Missing duration disables the time chart. Keep raw key/tempo secondary.
- Handle no-op results, identical alternatives and fewer than two movable entries. Retain explicit retry and navigation recovery. Add no player, auto-save, weight sliders or source-picker UI.

## Acceptance

An unfamiliar listener can choose a setting, compare every entry, identify what stayed in place and understand when there is no supported improvement. Capture desktop/narrow and light/dark screenshots. Check keyboard navigation, focus after async updates, announced status, reduced motion and graph text alternatives.

Extend HTTP contract tests only where behavior changed; no new frontend runner is required. Run `task check` and `git diff --check`.

## Comments

2026-09-06: The main listening purpose is an open product question. These controls implement the everyday-listening draft default. If the owner selects Journey, include its defined elapsed-time objective before finalizing this screen.

2026-09-06: Ticket 04 supplied the basic controls, unchanged/identical states, and API objective/component evidence. This ticket is now unblocked. Focus on complete metadata during analysis, factual coverage, original/suggested elapsed-time comparison and understandable transition explanations; do not rebuild the controls or expose the internal objective as a musical-quality percentage.

2026-09-06: Claimed at the owner's request. Keep metadata visible while analysis runs, add factual review/coverage, compare both orders over elapsed time, and validate keyboard/narrow/theme behavior with mocked services.

## Answer

2026-09-06: Implemented the review flow using the existing controls, tabs, Recharts and native disclosures. No player, source picker, auto-save or new frontend test framework was added.

| Before | After | Why |
| --- | --- | --- |
| The list arrived after audio work finished | Complete metadata appears first, with per-entry finding/measuring/checked/failure states | The listener can follow work without losing the playlist |
| Progress did not distinguish success from attempts | Completion, successful measurements and fixed-entry counts remain separate | A finished check can still lack usable audio evidence |
| A position-based tempo/intensity chart described one order | Original and suggested intensity share an elapsed-time axis, plus text timing tables | Long songs occupy their actual duration; missing intensity stays a gap |
| Transition match percentages | Assessment coverage and at most three supported listening notes | The product describes evidence without presenting cost as musical quality |
| Errors hid the list, and async updates could lose keyboard context | Last-loaded entries remain visible after failure; progress announcements and result focus are explicit | Retry/navigation and keyboard review remain usable |

The backend publishes metadata before starting source work, serializes parallel progress updates and updates duplicate occurrences together. Cached completions and fresh recording outcomes count consistently. Global interruptions stop pending labels and retain the complete last-loaded list. Sorting still requires the completed job and all prior revision/session protections.

The review counts original and suggested assessed boundaries separately. Notes are generated only for actual assessed neighbors, using supported intensity, tempo, texture or tonal changes, or a nearby credited-artist repeat. The reporting threshold suppresses weak sound evidence, and the neutral uncertainty prior is removed before deciding whether a change stands out. Notes never invent an edge across a fixed item or claim listener preference. Large-playlist uncomputed coverage remains unavailable rather than zero.

The Compare tab uses shared per-song intensity estimates for both orders. Step widths come from complete entry durations; the chart retains both sides of each boundary so unknown spans do not become ramps or zero-valued songs. Missing/invalid duration disables the time comparison. Expandable text tables show each song's start, end and qualitative intensity; tempo/key and detailed transition evidence remain secondary. Timing assumes full playback with crossfade off.

Validation: `task check` passed with 24 offline tests, lint/types and the production build; `git diff --check` passed. New HTTP checks observe full metadata and duplicate progress while analysis is blocked, distinguish attempted/successful checks, and retain entries after interruption. Note tests verify coverage, real neighbors, the three-note limit and suppression of weak/neutral evidence. The [native Node timeline check](../check_timeline.mjs) verifies ten-minute versus two-minute songs, unknown spans, invalid durations and clock formatting without a frontend test runner.

The [browser check](../check_preview.cjs) passed at 1280px light and 390px dark with reduced motion. It covers asynchronous profile/pin flows, focus after arranging, focus retained through analysis completion, navigation recovery without duplicate starts, progress/error visibility, listening notes, duration-aware tables, missing-duration fallback, horizontal keyboard scrolling and zero axe WCAG A/AA violations. All service responses were mocked.

Screenshots: [desktop analysis progress](../light-1280-analysis-progress.png), [mobile comparison](../dark-390-time-comparison.png), [desktop comparison](../light-1280-time-comparison.png), [interrupted check](../dark-390-interrupted-check.png).

Implementation locations: [job progress and API](../../../api/app.py), [review evidence](../../../api/playlist_sorter.py), [page and states](../../../frontend/src/components/playlist-page.tsx), [comparison](../../../frontend/src/components/song-details.tsx), [timeline helpers](../../../frontend/src/lib/review.ts).

Source/access permission and listener preference remain unverified as recorded earlier. No live media download or Spotify mutation was performed. Next frontier: ticket 06, verified saving and one safe session restore.
