# Generate Smooth and More variety arrangements with optional pins

Status: resolved
Type: task
Blocked by: 02, 03

Implement the bounded [arrangement objective and search](../spec.md#arrangement-contract) using complete entry identities and cached segment features.

## Work

- Add validated Smooth/More variety profiles and optional first/last occurrence IDs to the sort contract. Reject foreign entries, duplicate endpoint selection and fixed-slot conflicts.
- Calculate directed outro-to-intro costs, confidence-blended missing data, credited-artist spacing and five-entry monotony using the spec's explicit initial values. Share normalization and pair costs across candidate orders.
- Seed with a feasible baseline and at most four greedy starts. Improve with relocations/swaps under the two-pass/5,000-evaluation limit. Preserve fixed slots and pins throughout. Stable ties favor the baseline.
- Return the winning complete permutation, assessed-edge counts and component evidence for explanations. Identical profile results and an unchanged winner are legitimate results.
- Keep helpers callable with generated features and no network. Do not add a solver, model service, provider framework or user-adjustable weights.

## Acceptance

Use compact, table-driven fixtures to establish asymmetric transitions, half/double tempo, neutral unknown edges, independent duplicate placement, all-one-artist feasibility, fixed endpoints, conflicting pins and deterministic output. Candidate cost must never exceed the feasible baseline under the same objective. Validate all entries and hard constraints after every search result.

Benchmark cached 100- and 500-entry inputs against the spec's targets, recording the machine and elapsed times. Never truncate oversized playlists. Run `task check` and `git diff --check`.

## Comments

2026-09-06: Objective improvement establishes search correctness only. Listener preference belongs to ticket 07. Journey's progression term is explicitly disabled for the proposed first release.

2026-09-06: Claimed at the owner's request. Implement the objective, bounded search and pin validation with offline fixtures, connect the choices to the existing preview, and benchmark 100/500-entry arrangements.

## Answer

2026-09-06: Implemented Smooth and More variety with optional absolute first/last occurrence pins. The API rejects unknown profiles, foreign entries, duplicate endpoint choices and conflicts with fixed slots. Saving checks the complete displayed permutation and endpoint requirements again; unchanged orders are rejected as unnecessary saves.

Pure helpers in [playlist_sorter.py](../../../app/playlist_sorter.py) prepare shared normalization and directed outro-to-intro costs for tempo, intensity, texture and chroma. Half/double tempo is supported. Missing components blend toward neutral cost 0.5, and wholly unassessed edges remain exactly neutral. The objective includes all actual edges, credited-artist repetition over three preceding entries, and five-entry body-feature monotony, with the specified profile weights. The progression term remains disabled.

The search compares a feasible original baseline and up to four deterministic greedy starts, then improves the best seed through swaps and relocations in both directions. It rescans the complete directed objective for each trial, keeps the baseline on ties, and respects the two-pass/5,000-evaluation budget. Fixed entries remain in their slots throughout. Pair matrices are reused across profiles, and each profile caches only its latest result/choices. Above 1,000 entries, the full feasible baseline is returned with an explicit limited-search state, never a truncated playlist.

The existing page now exposes both styles and optional, clearable endpoint controls. Fixed endpoints are shown disabled with their reason. Pending choice changes disable saving until arranging again. Conflicting pins, unchanged results and identical results across the two profiles have explicit states. The API returns objective terms, assessed-edge counts and per-transition component costs/evidence for ticket 05's richer review. This ticket also removed the superseded Camelot-based greedy scorer and its unused constants module.

Validation: `task check` passed with 21 offline tests, Python/frontend lint/types and the production build; `git diff --check` and the offline SDK probe passed. Tests cover directed boundaries, tempo ambiguity, weak/missing evidence, hand-calculated objective values, duplicate/featured-artist spacing, fixed endpoints, invalid choices, deterministic ties, guard fallback, cached matrices, optional API inputs and stale/no-op save rejection. Existing session, cookie and interrupted-save protections remain passing.

The [browser check](../check_preview.cjs) passed with simulated asynchronous requests at 1280px light and 390px dark, reduced motion, keyboard selection/tabs/save, clearable options, conflicting pins, unchanged/identical results, fixed endpoints and zero axe WCAG A/AA violations. Screenshots: [desktop optional endpoints](../light-1280-optional-pins.png), [mobile controls](../dark-390-complete-preview.png).

Generated 100-entry arrangements took 0.12868 s for Smooth including matrix preparation and 0.11678 s for More variety reusing matrices. At 500 entries they took 0.28756 s and 0.20141 s. Each respected the evaluation cap and improved its feasible-baseline objective. [Benchmark method and limits](../../../docs/arrangement-benchmarks.md), [raw results](../arrangement-benchmark.jsonl).

These checks establish algorithm and interface behavior, not listener preference. All service interactions used mocks; live source/access questions remain under ticket 01's outcome. Next frontier: ticket 05.

Final browser-log follow-up: links styled as buttons now use native anchors with the existing shared button styles. This preserves link keyboard/role semantics and removes the UI library's native-button warning. Frontend lint/types/build and both browser scenarios passed again, including an assertion against that warning.
