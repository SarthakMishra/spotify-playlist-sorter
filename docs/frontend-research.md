# Frontend migration research

Checked on 2026-09-05. Sources below are official documentation, project-owned registry files, and npm metadata.

## Recommendation

Use a Vite React TypeScript app, React Router, Tailwind v4 and the requested shadcn preset. Build the frontend once and serve `frontend/dist` through FastAPI. Keep the current sequence: connect Spotify, pick a playlist, analyze its songs, pick the first song, preview the new order, and explicitly save it. Existing transition details and charts belong behind a disclosure. These requirements come from `api/app.py` and `README.md`.

The current app has no audio playback, genre filtering, file uploads or manual drag sorting. The registry research below identifies reusable options without adding those features to this migration.

## Versions and setup

The npm `latest` endpoints returned these stable versions. Commit the generated lockfile so installation is repeatable.

| Package | Version checked | Primary source |
| --- | --- | --- |
| React | 19.2.8 | [npm metadata](https://registry.npmjs.org/react/latest) |
| Vite | 8.2.2 | [npm metadata](https://registry.npmjs.org/vite/latest) |
| React Router | 8.3.1 | [npm metadata](https://registry.npmjs.org/react-router/latest) |
| Tailwind CSS | 4.3.3 | [npm metadata](https://registry.npmjs.org/tailwindcss/latest) |
| shadcn CLI | 4.21.0 | [npm metadata](https://registry.npmjs.org/shadcn/latest) |
| Vite React plugin | 6.1.1 | [npm metadata](https://registry.npmjs.org/@vitejs/plugin-react/latest) |

Vite requires Node 20.19+ or 22.12+, but React Router 8 raises the combined requirement to Node 22.22+. Use Node 24 LTS for builds. The local Node 26.7.0 meets the package requirements. [Vite requirements](https://vite.dev/guide/), [React Router package requirements](https://registry.npmjs.org/react-router/latest), [Node release status](https://nodejs.org/en/about/previous-releases).

The official shadcn Vite setup supports creating the app directly:

```bash
pnpm dlx shadcn@latest init --preset beEgoEQi --template vite --name frontend --no-monorepo
```

`--base base` can make the Base UI choice explicit. The preset itself does not encode that choice. Avoid generating a Next.js project or a monorepo for this app. [Vite installation](https://ui.shadcn.com/docs/installation/vite), [CLI options](https://ui.shadcn.com/docs/cli).

The official CLI preset decoder returned:

| Setting | Value |
| --- | --- |
| Style | `luma` |
| Base color, theme, chart color | `zinc` |
| Font | `inter` |
| Heading font | `inherit` |
| Icons | `lucide` |
| Radius | `default` |
| Menu color | `default` |
| Menu accent | `subtle` |

Keep the CLI-generated variables and component styling as the starting point. The create page could not be parsed by the browser tool, but the official decoder successfully resolved the exact supplied code. [Requested preset](https://ui.shadcn.com/create?preset=beEgoEQi), [preset inspection](https://ui.shadcn.com/docs/cli#preset).

Tailwind v4 has a dedicated `@tailwindcss/vite` plugin and starts with `@import "tailwindcss"`. Let the scaffold configure it; a legacy Tailwind v3 config and PostCSS setup are unnecessary. [Tailwind Vite installation](https://tailwindcss.com/docs/installation/using-vite).

## Routing, data and serving

- React Router's declarative `BrowserRouter` is sufficient for a small app with explicit API calls. Data mode adds loaders, actions and pending states if those remove existing fetch bookkeeping. Both support an SPA. Framework mode introduces its Vite plugin and route conventions; there is no need to adopt it solely to get client routing. Import current APIs from `react-router`. [Mode comparison](https://reactrouter.com/start/modes), [declarative installation](https://reactrouter.com/start/declarative/installation).
- If framework mode is chosen, `ssr: false` removes runtime SSR but still renders the root at build time. Browser APIs must therefore stay out of the initial render, and the project still needs `@react-router/node`. That complication is avoidable with a plain Vite SPA. [SPA mode](https://reactrouter.com/how-to/spa).
- Vite outputs `dist`; serve that bundle in production. `vite preview` is a local preview server. SPA routes need an index fallback so refreshing a playlist URL works. Keep API routes outside the fallback. [Vite deployment](https://vite.dev/guide/static-deploy), [React Router SPA deployment](https://reactrouter.com/how-to/spa).
- Use relative `/api/...` requests. In development, Vite's `server.proxy` forwards `/api` to FastAPI. Fix the development port with `strictPort` if it is part of the Spotify callback URL. [Vite server options](https://vite.dev/config/server-options).
- Keep Spotify secrets and tokens on the backend. `VITE_*` values are embedded in the browser bundle and cannot hold secrets. [Vite environment variables](https://vite.dev/guide/env-and-mode).
- A short polling loop is enough for the existing analysis progress callback. Clean up its timer and ignore or abort obsolete requests on playlist changes and unmount. React explicitly documents cleanup to prevent earlier responses from replacing newer state. Disable repeated submissions while actions are pending. [React effect cleanup](https://react.dev/reference/react/useEffect).

## Official components to reuse

The current catalog includes suitable components for every existing interaction. Add only those used. [Official component catalog](https://ui.shadcn.com/docs/components).

| Existing interaction | Component and implementation choice |
| --- | --- |
| Connect, analyze, sort, save | `Button`; `Input` and visible field labels only where setup actually needs input |
| Playlist and first-song selection | `Combobox` for searchable long lists; use stable IDs as values, since names can repeat |
| Song analysis | `Progress` with real done/total counts and a short status message |
| Playlist results | `Tabs` for "New order" and "Original"; a plain `Table` preserves song order |
| Failures and save status | `Alert` with a clear next action; keep durable failures visible |
| Transition details | `Accordion` or native disclosure containing the existing table and chart |
| Chart | Official `Chart` and Recharts v3, preserving the existing analysis |
| Playlist rows with artwork | `Item` supports media, title, description and actions if needed |

Base UI `Combobox` now supports object items through `itemToStringValue`, groups, custom items, and multiple selection with chips. No hand-built search popup or tag control is needed. `ProgressLabel` and `ProgressValue` supply visible labeling. [Combobox](https://ui.shadcn.com/docs/components/base/combobox), [Progress](https://ui.shadcn.com/docs/components/base/progress), [Item](https://ui.shadcn.com/docs/components/base/item).

Use the simple Table rather than introducing TanStack Table for a list whose order is the product's output. For charts, use CSS variables directly, such as `var(--chart-1)`, and give `ChartContainer` a height or minimum height so the responsive container can measure it. [Current chart guidance](https://ui.shadcn.com/docs/components/base/chart).

## External registries checked

The official directory includes `@reui`, `@kibo-ui`, `@elevenlabs-ui` and `@coss`. Namespaced installs use the shadcn CLI. Inspect source and dependencies with `view`, and preview project changes with `add --dry-run` before installing. [Directory](https://ui.shadcn.com/docs/directory), [directory data](https://ui.shadcn.com/r/registries.json), [CLI](https://ui.shadcn.com/docs/cli).

| Registry | Relevant reusable component | Assessment for this migration |
| --- | --- | --- |
| ReUI | Sortable, including a playlist example and keyboard interaction | Useful if manual track reordering becomes a requirement. The Base Luma item adds `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities` and about 12 KB of source. Existing sorting is automatic, so defer. [Docs](https://reui.io/docs/components/base/sortable), [playlist examples](https://reui.io/components/sortable), [registry item](https://reui.io/r/base-luma/sortable.json) |
| Kibo UI | Dropzone and Tags | Dropzone adds `react-dropzone`; Tags composes Badge, Button, Command and Popover. There is no file import or genre feature to migrate, and official Combobox already covers searchable chips. [Dropzone source](https://www.kibo-ui.com/r/dropzone.json), [Tags source](https://www.kibo-ui.com/r/tags.json) |
| ElevenLabs UI | Audio Player with shared playback, seek position, buffering and speed controls | A real reuse option if preview audio is added later. It expects playable URLs and currently adds Radix Slider and Dropdown Menu plus about 17 KB of source. Its website returned 403/429, so I inspected its official GitHub docs and registry payload. No player is needed for the current analysis-only product. [Docs source](https://github.com/elevenlabs/ui/blob/main/apps/www/content/docs/components/audio-player.mdx), [registry source](https://github.com/elevenlabs/ui/blob/main/apps/www/public/r/audio-player.json) |
| coss ui | Combobox, progress, table and other Base UI controls | `originui.com/selects` now redirects to coss ui. These overlap the official shadcn components and add no required capability. [Current library](https://coss.com/ui) |

Recommendation: use official shadcn components for this migration. None of the external items fills a gap in the existing workflow. Do not install a replacement library merely because it has a music demo.

## Simple copy and checks

Use "Connect Spotify", "Choose a playlist", "Check songs", "First song", "Sort playlist", "New order", "Original", "Save to Spotify", "Saved", and "Try again". Describe the main benefit as "Put your songs in a smoother order." Keep "Camelot", BPM and score explanations inside song details. Prefer "Checking songs... 12 of 40" over implementation terms.

Before handoff, run the production TypeScript/build checks, load a nested URL through FastAPI, and walk the flow with mocked API data. Check keyboard selection, visible labels, loading and empty states, errors, duplicate names, playlist switching during analysis, and save confirmation. A real Spotify account is required for the final external integration check.

## Updated toolchain requirements

The user subsequently requested pnpm, Oxlint, Oxfmt and strict TypeScript checks. Use pnpm for installation, scripts and registry commands. Keep its version in `packageManager` and commit only `pnpm-lock.yaml`. The scaffold's ESLint and Prettier dependencies can be removed after Oxc checks replace them.

Fresh npm metadata returned Oxlint 1.81.0, `oxlint-tsgolint` 7.0.2001, Oxfmt 0.66.0 and TypeScript 7.0.2. These supersede the scaffold's TypeScript 6.0.3. The installed pnpm 11.24.0 is suitable; the registry's latest was 11.25.0. [Oxlint metadata](https://registry.npmjs.org/oxlint/latest), [type-aware engine metadata](https://registry.npmjs.org/oxlint-tsgolint/latest), [Oxfmt metadata](https://registry.npmjs.org/oxfmt/latest), [TypeScript metadata](https://registry.npmjs.org/typescript/latest), [pnpm metadata](https://registry.npmjs.org/pnpm/latest).

```bash
pnpm add -D oxlint@latest oxlint-tsgolint@latest oxfmt@latest typescript@latest
```

Oxlint type-aware mode requires the separate `oxlint-tsgolint` package and TypeScript 7 compatible configuration. Oxlint 1.81.0 declares a peer requirement of `oxlint-tsgolint >=7.0.2001`. The native engine does not need a parallel ESLint process. Keep `tsc -b` for compiler diagnostics because the Oxlint config reference still labels its combined `typeCheck` option experimental. TypeScript 7 uses the `tsc` command, despite older preview documentation showing `tsgo`. [Type-aware setup](https://oxc.rs/docs/guide/usage/linter/type-aware.html), [config reference](https://oxc.rs/docs/guide/usage/linter/config-file-reference.html), [Microsoft's native compiler repository](https://github.com/microsoft/typescript-go).

A strict `.oxlintrc.json` starting point:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["typescript", "unicorn", "oxc", "react", "jsx-a11y", "import"],
  "categories": {
    "correctness": "error",
    "suspicious": "error",
    "perf": "error"
  },
  "options": {
    "typeAware": true,
    "maxWarnings": 0,
    "reportUnusedDisableDirectives": "error"
  },
  "env": { "browser": true },
  "ignorePatterns": ["dist"],
  "rules": {
    "react/react-in-jsx-scope": "off",
    "react/rules-of-hooks": "error",
    "typescript/no-explicit-any": "error",
    "typescript/no-non-null-assertion": "error",
    "typescript/no-misused-promises": "error",
    "typescript/no-unsafe-argument": "error",
    "typescript/no-unsafe-assignment": "error",
    "typescript/no-unsafe-call": "error",
    "typescript/no-unsafe-member-access": "error",
    "typescript/no-unsafe-return": "error",
    "typescript/switch-exhaustiveness-check": "error"
  }
}
```

I checked the exact rule names and categories using `pnpm dlx oxlint@1.81.0 --rules --format json` outside the repository. The `react` plugin includes hooks and refresh rules; `jsx-a11y` is built in. Enabling a plugin makes its rules available, while categories and explicit rules enable checks. Setting `plugins` replaces the defaults, which is why the default TypeScript, Unicorn and Oxc plugins remain in the list. [Plugin behavior](https://oxc.rs/docs/guide/usage/linter/plugins.html), [categories](https://oxc.rs/docs/guide/usage/linter/config.html).

`react/rules-of-hooks` and the unsafe-value rules are outside the chosen categories, so list them explicitly. `react/exhaustive-deps` and `typescript/no-floating-promises` already belong to correctness. Turn off `react/react-in-jsx-scope` because the project uses React's automatic JSX transform. This is a compatibility setting, not a directory exemption. Broad React categories also enable native React Compiler checks, which the project currently labels experimental. Diagnose any false positive narrowly; keep hooks and accessibility checks active. [JSX rule guidance](https://oxc.rs/docs/guide/usage/linter/rules/react/react-in-jsx-scope.html), [hooks rule](https://oxc.rs/docs/guide/usage/linter/rules/react/rules-of-hooks.html), [compiler rule status](https://oxc.rs/docs/guide/usage/linter/plugins.html).

For `.oxfmtrc.json`, retain formatter defaults and add Tailwind sorting:

```json
{
  "$schema": "./node_modules/oxfmt/configuration_schema.json",
  "sortTailwindcss": {
    "stylesheet": "./src/index.css",
    "functions": ["cn", "cva"]
  },
  "ignorePatterns": ["dist", "pnpm-lock.yaml"]
}
```

Oxfmt includes Tailwind class sorting without a separate Prettier plugin. The v4 stylesheet path is relative to the formatter config. Function names are exact matches. Package field sorting is already enabled by default; import sorting is optional and can be enabled with `sortImports: {}`. `oxfmt --check .` checks formatting, while `oxfmt --write .` changes files. Bare `oxfmt` writes by default, so CI must use `--check`. [Sorting](https://oxc.rs/docs/guide/usage/formatter/sorting.html), [formatter options](https://oxc.rs/docs/guide/usage/formatter/config-file-reference.html), [CLI](https://oxc.rs/docs/guide/usage/formatter/cli.html).

Apply strict compiler options to both the app and Vite configuration projects:

```json
{
  "strict": true,
  "noUncheckedIndexedAccess": true,
  "exactOptionalPropertyTypes": true,
  "noImplicitOverride": true,
  "noImplicitReturns": true,
  "noFallthroughCasesInSwitch": true,
  "noUnusedLocals": true,
  "noUnusedParameters": true,
  "noPropertyAccessFromIndexSignature": true,
  "noUncheckedSideEffectImports": true,
  "allowUnreachableCode": false,
  "allowUnusedLabels": false,
  "forceConsistentCasingInFileNames": true,
  "skipLibCheck": false
}
```

`strict` enables the strict family but does not include every option above. Indexed reads must account for missing values, and optional properties no longer silently accept explicit `undefined`. Fix actual component types or omit absent props instead of excluding generated shadcn files. [Strict family](https://www.typescriptlang.org/tsconfig/strict.html), [indexed access](https://www.typescriptlang.org/tsconfig/noUncheckedIndexedAccess.html), [optional properties](https://www.typescriptlang.org/tsconfig/exactOptionalPropertyTypes.html), [index signatures](https://www.typescriptlang.org/tsconfig/noPropertyAccessFromIndexSignature.html).

Keep `moduleResolution: "bundler"`, `module: "esnext"`, `verbatimModuleSyntax`, `erasableSyntaxOnly`, `noEmit` and `jsx: "react-jsx"`. Keep explicit environment `types` for the app and Vite config. Do not restore `baseUrl` from older shadcn examples: relative `paths` values work without it, and TS6 deprecated it before TS7 removed support. TS6 already enabled strict mode and side-effect-import checking by default, but explicit settings make the project's requirements clear. [Compiler changes and migration](https://www.typescriptlang.org/docs/handbook/release-notes/typescript-6-0.html), [side-effect imports](https://www.typescriptlang.org/tsconfig/noUncheckedSideEffectImports.html).

Suggested scripts are `lint: oxlint .`, `lint:fix: oxlint --fix .`, `format: oxfmt --write .`, `format:check: oxfmt --check .`, and `typecheck: tsc -b --pretty false`. The build should run type checking before `vite build`. Run the installed tools through pnpm scripts and use `pnpm install --frozen-lockfile` in CI.

## Implementation notes

The user chose pnpm after scaffolding. All repository `node_modules` directories and the npm lockfile were removed, then dependencies were installed with pnpm. The version is pinned in `package.json`; CI and Docker use frozen installs. [pnpm install](https://pnpm.io/cli/install), [pnpm Docker](https://pnpm.io/docker)

The strict lint pass found unused generic chart helpers and unsafe payload handling in the generated chart wrapper. The app uses the already-installed Recharts `ResponsiveContainer`, `Tooltip` and `LineChart` directly, retaining the chart behind the song-details disclosure. The unused wrapper was removed. Recharts' transitive Redux Toolkit declarations currently fail strict TypeScript 7 exact-optional checks, so `skipLibCheck` is enabled for declaration internals. All application and owned shadcn source still receives strict compiler and Oxlint checks. The input-group wrapper also drops its optional click-to-focus behavior on non-interactive containers; native inputs and buttons retain keyboard interaction.


## Verification

The final production bundle passed TypeScript, type-aware Oxlint and Oxfmt checks. A Chromium walkthrough covered the full mocked API flow, keyboard song selection, duplicate rows, original/new-order tabs, lazy chart loading, saving, reload and expired-session recovery. Axe reported no WCAG A/AA violations on the connect screen, preview and details views across desktop/light and mobile/dark checks.

A local mobile Lighthouse run scored 98 for performance, 100 for accessibility and 100 for best practices, with LCP 2.1 seconds and CLS 0. These are local lab results, not production measurements. Enabling FastAPI gzip and loading the playlist editor only on its route reduced the initial JavaScript transfer to about 111 KB. Live Spotify/YouTube integration still requires an account check.

Editor recommendations use the official Ruff, Astral ty and Oxc extensions. Oxc inherits the project's type-aware config and discovers the nested frontend binaries. [ty editors](https://docs.astral.sh/ty/editors/), [Oxc editors](https://oxc.rs/docs/guide/usage/linter/editors.html)
