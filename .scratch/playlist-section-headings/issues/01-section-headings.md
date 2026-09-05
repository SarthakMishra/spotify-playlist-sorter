# Playlist section headings

Status: resolved
Type: task

Make First song and Playlist preview a little bigger. Move "We'll start here and order the rest for you." below First song and match the styling and title spacing of "Review the order before saving."

## Comments

Use existing Tailwind typography and spacing utilities. Preserve the First song input label.

## Answer

Increased both titles from 14px to 16px with matching semibold weight. Moved the first-song description directly below its title, using the preview description's 14px muted text and 4px title spacing.

Validated matching computed styles, keyboard focus, light and dark themes, and a 375px viewport with no overlap or horizontal overflow. Captured desktop and mobile screenshots in the browser. `task check` and `git diff --check` passed.
