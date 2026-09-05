# Preview tab spacing and background

Status: resolved
Type: task

Add more space below the playlist preview tabs and soften their background, especially in dark mode.

## Comments

Increase the tabs-to-content gap from 8px to 16px. Use the existing muted background at 70% opacity in light mode and 50% in dark mode.

## Answer

Applied both changes to the playlist preview using existing Tailwind classes.

`task check` and `git diff --check` passed. Verified the 16px gap, both theme backgrounds, keyboard tab selection, and no horizontal overflow at 375px. Captured light desktop and dark mobile screenshots in the browser.
