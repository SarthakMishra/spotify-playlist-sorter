# Playlist hover spacing

Status: resolved
Type: task

Add left padding within playlist links and a gap between their hover background and the list dividers.

## Comments

Use existing Tailwind spacing utilities and preserve the row height.

## Answer

Added 12px of padding inside each playlist link and 4px above and below it, preserving the total row height.

Validated in the browser with light and dark themes, a narrow viewport, and keyboard focus. Confirmed 12px left padding, 4px clearance from each divider, and no horizontal overflow. `task check` and `git diff --check` passed.
