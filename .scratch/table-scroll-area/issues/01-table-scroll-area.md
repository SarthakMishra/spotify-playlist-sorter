# Rounded table scroll areas

Status: resolved
Type: task

Replace native table scrollbars with shadcn Scroll Area so they stay within the rounded containers. Preserve the height limit, sticky headers, horizontal scrolling, and accessible keyboard navigation across all table views.

## Comments

Reproduced at 375x640: the shared native overflow wrapper reserves a 15px scrollbar gutter along its rounded edge. All table views use this wrapper, so the replacement belongs in the shared Table component. This direct reproduction makes broader hypothesis testing unnecessary.

Use the base-luma Scroll Area from the shadcn registry and the already installed Base UI primitives.

Reference: https://ui.shadcn.com/docs/components/base/scroll-area

## Answer

Replaced the shared native wrapper with shadcn Scroll Area and both custom scrollbar orientations. The root clips to its rounded border, while the named keyboard-focusable viewport preserves the height limit and sticky headers. Scrollbars stay above the sticky header so the entire thumb remains draggable.

The browser check failed on the native wrapper and passes for new order, original order, song details, and transitions. Verified both axes at 375px, desktop layout, light and dark themes, and PageDown scrolling. `task check` and `git diff --check` passed. No dependencies were added.

Browser validation uses [check.js](../check.js) with [fixture.js](../fixture.js) as an isolated-page navigation init script.
