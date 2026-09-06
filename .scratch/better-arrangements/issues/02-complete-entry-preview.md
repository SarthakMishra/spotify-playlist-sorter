# Make the preview match the complete saved playlist

Status: resolved
Type: task
Blocked by: none

The current preview excludes unchecked entries while the save keeps them at their original positions. Fix the complete-entry contract in the [specification](../spec.md#one-complete-order-throughout-the-product).

## Work

- Retain metadata/placeholders for every item in `_fetch_tracks_from_spotify` and `load_playlist`. Assign snapshot-scoped occurrence identities once. Keep recording IDs separate from entry identity.
- Carry the complete original and proposed entry sequences through API models, comparison, transition analysis and frontend tables. Measurements can be absent. Never regenerate duplicate identities from their new order.
- Replace the ID-list-only sorting/save boundary with occurrence permutations. Adapt the current sorter enough to preserve independent duplicate entries and fixed slots; the richer objective comes in ticket 04.
- Reuse the existing range-move writer and all stale/session/multiset protections. Validate every entry occurs exactly once, fixed positions remain fixed, and the displayed permutation is the saved permutation.
- Show actual positions, fixed reasons and unknown transitions. Show the full unchanged list when nothing can be analyzed; this is not an empty playlist or a successful optimization.

## Acceptance

Extend `tests/test_api.py:test_browser_flow_and_safe_reordering` so both preview and mocked Spotify readback equal `[B, unchecked, A, unavailable, A]`. Test duplicate identities, local/non-track placeholders, entirely unchecked playlists and revision rejection. An unchecked item between B and A must prevent an explanation that says B leads directly into A.

Run `task check` and `git diff --check`. Check the complete list with keyboard navigation and a narrow viewport. Update the proposed ADR when the contract ships.

## Comments

2026-09-06: This is the first product correction to implement. It does not depend on improved audio analysis or live-source resolution.

2026-09-06: Claimed at the owner's request. Trace and update the complete entry contract through analysis, sorting, preview, and range-move saving, with offline and browser checks.

## Answer

2026-09-06: Implemented. The same full occurrence permutation now drives the preview, transition details and Spotify range moves. Source playlist/snapshot/position identities remain stable through sorting and repeated saves. Every item retains its metadata or an unavailable placeholder, and fixed entries retain their original slots.

The first-song control selects a specific occurrence and labels its original position. If the opening item is fixed, the control says First song to move and targets the first available slot. Absolute opener/closer pins remain ticket 04 work. The existing greedy score still determines known adjacent choices; after an unassessed fixed boundary, the sorter uses the next available original entry instead of assuming a transition across the gap.

Unanalyzed songs, local files, episodes and unavailable items show a reason. Zero or one movable song leaves the full original list visible with a retry action and no sort/save action. Details retain actual neighbors, show Not assessed for unknown transitions, and leave chart gaps with markers for isolated measurements.

The failing browser-flow regression now verifies both preview and mocked Spotify order as `[B, unchecked, A, unavailable, A]`. It also selects the second copy of A and saves again, verifying the exact occurrence positions. Additional cases cover sparse metadata, all-fixed/one-movable playlists, a fixed opener, partial features, malformed permutations, foreign occurrences and actual transition neighbors. Existing stale-preview, session, interrupted-save and read-only-cookie checks remain passing.

Validation: `task check` passed, including seven offline tests and the production build; `git diff --check` and the updated offline SDK probe passed. Browser checks covered 1280px light and 390px dark views, reduced motion, keyboard duplicate selection, tab activation and saving, all-fixed/fixed-opener states, and zero axe WCAG A/AA violations. All browser API requests used invented fixtures; no live Spotify changes or audio downloads occurred.

Screenshots: [desktop preview](../light-1280-complete-preview.png), [mobile preview](../dark-390-complete-preview.png), [details](../light-1280-details.png), [unchecked mobile playlist](../dark-390-unchecked.png). The [browser check](../check_preview.cjs) can run against an isolated Vite server with Playwright available through `NODE_PATH`.

The [ADR](../../../docs/adr/0001-arrange-playlist-entries.md) is accepted. The next frontier is ticket 03, recording matching and analysis.
