# Move transient playlist alerts into toasts

Status: resolved
Type: task

Move failed progress checks and analysis requests into the existing toast system, with retry actions. Audit other alerts in the current worktree. Keep field validation, configuration blockers, and interrupted-save warnings visible beside the content they explain. Dismissing a toast must not prevent recovery, and navigating away must clear its playlist-specific actions.

## Comments

The progress polling catch and analysis request catch share the inline error banner shown in the report. Other request failures already use toasts. Verify the actual mocked browser flow, including retries and navigation, then run `task check` and `git diff --check`.

## Answer

Progress polling and analysis request failures now use dismissible toasts with retry actions. Retry also remains available on the page after dismissal. Retrying or navigating away clears the playlist's error toast. Interrupted-save warnings remain visible independently.

The YouTube access page added to the worktree during this pass now uses toasts for successful updates and request failures. Cookie-file validation stays inline. Spotify setup blockers, failed-page states, another playlist's active job, and first/last entry validation also remain inline because they explain unavailable content or controls.

Toast actions now sit below the message, fixing the unreadable narrow text column at 320px without adding dependencies.

Validation: the [browser check](../check.cjs) passed at 1280px/light, 390px/dark, and 320px/light with mocked API requests. It covers the reported fetch failure, request retry, dismissal and recovery, navigation cleanup, interrupted saves, keyboard access, and YouTube feedback/validation. Accessibility checks exclude Base UI's invisible focus guards and inspect urgent toasts while focused, when Base UI exposes their controls. Frontend lint, formatting, types, production build, and `git diff --check` passed. `task check` stops on two existing Python lint errors in `app/youtube.py`.

Screenshots: [desktop](../light-1280-polling-error.png), [dark mobile](../dark-390-polling-error.png), [320px](../light-320-polling-error.png).

The separate final `task test` run also reports five failures in the existing Python worktree. No Python files were changed for this task.
