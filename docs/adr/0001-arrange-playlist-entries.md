---
status: accepted
---

# Arrange complete playlist entries

Represent an arrangement as a permutation of the complete playlist's occurrence identities, scoped to its source snapshot, and share audio measurements separately by recording. The previous unique-track-ID approach grouped duplicates and omitted fixed entries from previews; carrying full entries through sorting and saving makes the preview describe the order the listener will actually hear.

Implemented in [ticket 02](../../.scratch/better-arrangements/issues/02-complete-entry-preview.md). Keep occurrence identities tied to the loaded source order while tracking the current saved order separately, so another sort/save cannot confuse duplicate entries. The endpoint pins added in [ticket 04](../../.scratch/better-arrangements/issues/04-arrangement-objective.md) use these identities, and saving validates them again. See the [specification](../../.scratch/better-arrangements/spec.md).
