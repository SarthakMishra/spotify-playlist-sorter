# Verify saved order and allow one safe restore during the session

Status: resolved
Type: task
Blocked by: 02

Extend the existing writer and session job for the [save and restore behavior](../spec.md#save-and-listen). Work uses mocked Spotify; live verification requires ticket 01 and a separately authorized target playlist.

## Work

- Bind save to the exact complete preview and current source snapshot. Keep retries disabled for ambiguous mutations, existing CSRF checks and one active session action.
- Retain the complete pre-save order in the session. After successful moves, fetch a snapshot-consistent full playlist and compare it with the target, including duplicate counts and fixed placeholders. Report Saved only after verification.
- Expose Restore previous order only after a verified save. Bind it to the observed post-save snapshot and last successful operation. Restore uses range moves and readback as well.
- Remove restore eligibility on external changes, uncertain save/readback, fresh playlist analysis or session loss. State that restore lasts only for the current session and most recent save.
- On partial failure, invalidate the mutation state and require a fresh read. Do not auto-rollback or replay a possibly successful move. Do not add replacement writes or a persistent history store.

## Acceptance

Extend the existing save tests for successful save/restore, stale revision, external edit before restore, a failure after one successful move, a lost response, changed playlist during readback and unavailable entries. No path invokes playlist replacement, and no failed verification produces a Saved confirmation.

Run `task check` and `git diff --check`. Manually check save/restore action labels and the session-lifetime explanation.

## Comments

2026-09-06: Permanent recovery/history is deferred. The existing single-process session lifetime makes a narrowly described one-level restore the smallest useful first version.


## Answer

Implemented on 2026-09-06. Saves and restores use the existing range-move writer with zero retries. Before any move and after the last move, the writer reads all pages between matching snapshots and compares the complete provider sequence against the expected occurrence order. A missing move snapshot stops further writes. Only a verified result advances the saved order and enables Restore previous order.

The sorter belongs to the session job and retains one complete pre-save occurrence order. Another preview preserves it; another successful save replaces it. Restore ignores newer preview pins, verifies the observed post-save snapshot and full current order, and consumes the previous order after success. The API binds both actions to the current revision and CSRF token and stays busy through verification. Fresh analysis, session loss, an observed external edit, or an uncertain write/readback removes eligibility. There is no replacement write, rollback, replay or persistent history.

The screen offers Open Spotify and Restore previous order after verification, explains the session limit beside restore, and shows the verified restored sequence with its own label after use. Failure shows Check again and the last loaded order. Restoration clears endpoint pins and removes the old arrangement score and listening notes.

Verification uses provider type/ID/URI, local status and available added-at/added-by metadata. Identical copies or null placeholders without distinguishing provider metadata cannot be individually identified by readback; their counts and positions are checked, while occurrence tracking and snapshot constraints preserve the intended move sequence. External changes are detected when the next save or restore is attempted, not through background Spotify polling. A successful readback confirms the observed snapshot, not a guarantee against future Spotify edits.

Validation:

- `task check`: passed lint, formatting, Python/TypeScript checks, **31 offline tests** and the production build.
- [Write regressions](../../../tests/test_playlist_writes.py) and the expanded [HTTP flow](../../../tests/test_api.py) cover paginated reads, successive saves/latest restore, duplicate occurrence metadata, local/episode/null items, missing snapshots, stale revisions, source mismatch, external edits, partial writes/lost responses, changed or incomplete readback, restore failure, session loss and concurrent action rejection through verification.
- [Browser check](../check_preview.cjs): keyboard save/restore, focus, action labels, lifetime copy, actual restored sequence, stale-restore recovery, existing preview/progress comparisons and axe checks passed at 1280px/light and 390px/dark. Screenshots: [saved](../light-1280-verified-save.png), [restored](../dark-390-restored-order.png).
- `git diff --check`: passed. All provider activity used mocks; no live Spotify mutation, source download or listening pilot was performed.

Ticket 07 now has its engineering dependencies resolved, but remains `needs-info` for authorized audio and real listening observations. Ticket 08 is also ready for implementation.
