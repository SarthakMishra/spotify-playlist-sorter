# Header theme switcher

Status: resolved
Type: task

Align the top bar with the main content and provide compact, labeled Refresh, theme, and Sign out buttons using the original ghost styling.

## Comments

- Cycle Light, Dark, and System on click, defaulting to System, with Sun, Moon, and Monitor icons.
- Remember the choice after reload and keep following OS changes in System mode.
- Reuse the existing Button with the ghost variant and small size, an 8px icon-to-label gap, and muted text/icons that use the foreground color on hover or keyboard focus.
- Move Refresh playlists to the top bar and match its inner width to the page content.
- Fade the bottom divider from the page background at both edges to the existing border color at its midpoint.
- Check keyboard interaction, both themes, and a narrow viewport.

Reference: https://ui.shadcn.com/docs/dark-mode/vite

System icon: https://lucide.dev/icons/monitor

## Answer

Aligned the header with the 672px page column and moved Refresh playlists into the header. All three controls have visible labels and use the original small ghost-button styling, with no default background. The controls wrap below the app name on narrow screens.

Each button has an 8px gap between its icon and text. Both use muted foreground at rest and the normal foreground on hover or keyboard focus. The 1px bottom divider fades from the page background at each edge to the existing border color at the midpoint, using the current theme's tokens.

The theme button cycles Light, Dark, and System with Sun, Moon, and Monitor icons. Preferences persist after reload and System follows live OS changes. The unused dropdown component was removed. No dependencies were added.

Validation passed: `task check`, `git diff --check`, [browser self-check](../check.js), keyboard activation, persistence after reload, and header alignment at desktop, 375px, and 320px widths. Refresh disables during loading, makes one playlist request, and updates the displayed song count.

Verified the final spacing, hover/focus colors, and gradient stops in both light and dark themes.

Screenshots: [dark mobile](../dark-mobile.png), [light desktop](../light-desktop.png).
