# Issue tracker: Local Markdown

Issues and specs live as Markdown files under `.scratch/`.

## File conventions

- Use one directory per feature: `.scratch/<feature-slug>/`.
- Store the spec in `spec.md`.
- Store each implementation ticket in `issues/<NN>-<slug>.md`, numbered from `01`.
- Record triage state near the top as `Status: needs-triage`, using the mapping in `triage-labels.md`.
- Append discussion under `## Comments`.

## Publishing and reading

When a skill says to publish to the issue tracker, create the appropriate
spec or issue file under the feature directory.

When a skill says to fetch a ticket, read its referenced path. Resolve ticket
numbers within their feature directory.

## Wayfinding operations

- Map: `.scratch/<effort>/map.md`, containing Notes, Decisions-so-far, and Fog.
- Child ticket: `issues/<NN>-<slug>.md`, with a `Type:` of `research`, `prototype`, `grilling`, or `task`.
- Dependencies: record `Blocked by: 01, 02` near the top. A ticket becomes unblocked when every listed ticket is resolved.
- Frontier: select the first numbered unresolved, unblocked, unclaimed ticket.
- Claim: set `Status: claimed` and save before starting work.
- Resolve: append the result under `## Answer`, set `Status: resolved`, and add a brief result and link to the map's Decisions-so-far section.

The execution statuses `claimed` and `resolved` supplement the triage statuses.
