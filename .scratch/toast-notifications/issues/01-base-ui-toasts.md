# Base UI toast notifications

Status: resolved
Type: task

Use shadcn's Base UI toasts for transient action feedback, including successful saves and request errors. Show sorting and saving progress outside the document flow so starting work does not shift the playlist controls or preview. Use the installed Base UI dependency, without Sonner.

Keep lasting guidance and recovery information visible, including analysis progress, failed jobs, interrupted saves, and songs that could not be checked. Check success, failure, retry, navigation, keyboard dismissal, both themes, and narrow viewports.

## Comments

Component reference: https://ui.shadcn.com/docs/components/base/toast

## Answer

Installed shadcn's Base UI toast component using the existing dependencies. Sorting and saving show a persistent loading toast, then update it to success or failure. Starting either operation leaves the playlist controls and preview in place. Successful saves, rejected requests, and sign-in/sign-out failures use timed, dismissible notifications.

Loading toasts clear on navigation and resume when returning to a running job. Reopening a completed job does not replay its success notification. Analysis progress, polling recovery, failed jobs, and unavailable-song warnings remain visible on the page. Interrupted-save warnings survive toast dismissal.

The component uses the existing theme and Button styles, respects reduced motion, and accounts for the mobile bottom safe area. No dependency or lockfile changes were needed.

Validation passed:

- `task check` and `git diff --check`.
- [Browser self-check](../check.js) with mocked API responses on desktop and mobile. Covers stable sorting/saving layout, single-toast completion, auto-dismissal, immediate completion, rejected requests, polling recovery, interrupted saves, and sign-out errors.
- Navigation cleanup and resumption, no success replay on reopening a saved playlist, and one-time OAuth error notification with unrelated query parameters preserved.
- F6, Tab, and Enter to focus and dismiss a toast, plus light/dark rendering and no overflow at 375px and 320px widths.

Screenshots: [sorting on desktop](../sorting-desktop.png), [transient error on mobile](../error-mobile.png).
