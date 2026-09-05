# Domain docs

This repository uses a single-context layout across the Python backend and
React frontend.

## Read before exploring

Read root `CONTEXT.md` for domain terminology and relevant files in
`docs/adr/` for architectural decisions.

If these files are absent, proceed silently. The `domain-modeling` skill
creates them when terms or decisions are resolved.

## Layout

- `CONTEXT.md`: shared domain glossary and model.
- `docs/adr/NNNN-short-decision-name.md`: numbered architectural decisions.

## Consumer rules

Use the glossary's terms in issue titles, proposals, hypotheses, and tests.
If a needed concept is missing, reconsider the terminology or record the
gap for domain modeling.

Explicitly identify any proposal that contradicts an existing ADR and
explain why the decision should be revisited.
