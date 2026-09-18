---
name: write-ux-copy
description: Write, rewrite, critique, or systematize UX and product-interface copy for web, mobile, desktop, and conversational interfaces. Use for navigation and feature names, buttons, links, forms, helper text, validation, errors, empty and first-run states, onboarding, permissions, notifications, settings, confirmations, destructive actions, success and status messages, loading and offline states, search and filtering, account and billing flows, admin and role controls, data-heavy products, and AI features. Also use to produce copy decks, UI copy tables, content inventories, terminology systems, or copy audits from designs, screenshots, requirements, or code. Do not use for marketing pages, ads, long-form editorial writing, or general brand voice work unless that text is embedded in a product flow.
---

# Write UX Copy

Treat words as controls, wayfinding, feedback, and risk management—not decoration. Produce copy that helps a person understand where they are, what happened, what they can do, and what will happen next.

Ground this practice in Basecamp's principle that every interface word is a design decision and in observed HEY/Basecamp patterns: plain audience language, concrete verbs, question-led forms, adjacent explanations, instructive empty states, and explicit consequences. Borrow the reasoning, not their house voice.

## Start with the interaction

Before drafting, reconstruct the interface state. Infer missing details when low-risk; ask only when ambiguity would materially change the action or consequence.

Capture:

- **Person:** expertise, permissions, language, emotional state, accessibility needs.
- **Intent:** the job they came to complete, not the feature the team built.
- **Entry:** what they just did or what brought them here.
- **State:** new, active, empty, partial, complete, failed, blocked, expired, or offline.
- **Object:** the noun being viewed or changed.
- **Action:** the immediate verb available.
- **Consequence:** what changes, who is affected, when it happens, whether it can be undone.
- **Recovery:** the next useful move if the action cannot succeed.

Do not polish isolated strings without checking their neighbors. A title, explanation, control, and feedback message form one interface sentence even when they appear in different components.

## Design the copy

1. **Write the one-sentence interaction contract.** Use: “Here, `[person]` can `[action]` to `[outcome]`; this affects `[scope]` and can/cannot be undone.”
2. **Choose the product vocabulary.** Give one stable name to each user-visible object and one clear verb to each action. Prefer the audience's words over database, API, policy, or team language.
3. **Set the hierarchy.** Decide what belongs in the title, supporting text, label, helper text, primary action, secondary action, and feedback. Do not make one component carry the whole explanation.
4. **Draft the primary path first.** Make the next move evident without documentation. Then write empty, partial, loading, success, error, permission, and destructive states.
5. **Place explanations at the decision.** Explain unfamiliar concepts before a choice, constraints beside the field, and consequences before commitment.
6. **Read in the rendered context.** Check truncation, repetition, hierarchy, control order, variable data, screen-reader meaning, and whether the words still work without an icon.
7. **Edit for precision.** Remove words that do not change understanding or confidence. Restore any word whose removal makes scope, timing, consequence, or recovery ambiguous.

For component-specific rules and bad-versus-good examples, read [references/interface-patterns.md](references/interface-patterns.md). Read only relevant sections when the task is narrow; read the whole file for a product-wide audit or copy system.

For source-derived HEY/Basecamp principles and representative interface evidence, read [references/hey-basecamp-evidence.md](references/hey-basecamp-evidence.md) when establishing a voice direction, explaining a recommendation, or checking whether a draft reflects the requested source material. Do not treat captured strings as a template library.

## Core rules

### Write from the person's point of view

- Name the object they recognize: “project,” “invoice,” “sender,” or “team member,” not “record,” “entity,” “resource,” or “user object.”
- Describe the visible outcome, not the implementation: “Email invitation” rather than “Trigger invite workflow.”
- Use “you” and “your” when it removes ambiguity. Avoid repeatedly narrating the product as “we.”
- Match expertise. Do not oversimplify established professional terms, but explain terms the intended audience may not know.

### Make controls predict outcomes

- Lead action labels with a specific verb: “Create project,” “Send reminder,” “Download CSV,” “Remove access.”
- Avoid “Submit,” “Continue,” “OK,” “Yes,” and “Confirm” when the outcome can fit on the control.
- In this app's questionnaire, use `Next` between steps and `Calculate my plan` for the final action.
- Let a staged control disclose the next step: “Next: choose projects.” Use an ellipsis only when the action opens another decision or requires more input, never as decoration.
- Pair destructive labels with the affected object: “Delete invoice,” not “Delete.”
- Use a noun label only for navigation or a mode, not for an action.

### Explain only what earns its place

Explanation is valuable when a person may misunderstand a novel concept, meaningful consequence, unusual constraint, or difference between choices. It is noise when it restates the label or describes ordinary UI mechanics.

Prefer this sequence:

1. What this is.
2. Why it matters now.
3. What the person can do.
4. What will happen.

Do not force all four into every state. Use the smallest subset that closes the actual knowledge gap.

### Be brief, not cryptic

- Put the decision first; background follows.
- Use short sentences and concrete examples when they explain faster than abstractions.
- Remove greetings, apologies, and enthusiasm from routine system messages.
- Keep necessary details even when they make high-stakes copy longer: affected data, audience, charge, timing, reversibility, and recovery.
- Prefer progressive disclosure over a wall of pre-emptive prose.

### Use personality in the safe places

Human language, contractions, analogy, and light play can make unfamiliar ideas memorable. Never let personality obscure an error, legal choice, permission, payment, destructive action, security event, health issue, or accessibility instruction.

Create distinctive terms only when the product introduces a genuinely distinct mental model and can teach it in context. A name such as HEY's “Paper Trail” works because a plain definition sits beside it. Without teaching, novelty becomes vocabulary debt.

### Keep context above mechanical consistency

Use the same term for the same object. Do not require the same button word in every context when outcomes differ. “Save,” “Create project,” “Start collecting answers,” and “Email invitation” may all be correct for different commitments.

### Use a small product vocabulary

For a product that estimates tax and organizes supported actions, use:

- `My Next Filing` for the product.
- `your estimate` for the calculation.
- `your plan` for the result, dates, and actions.
- `your saved workspace` for persisted browser state.
- `this app` when explaining scope or limitations. Use `this version of the app` only when a release change matters, such as a change to saved-data compatibility.

Avoid using `this check` as the default name for the product or journey. Use `check` when it describes an actual action, such as `Check these answers`. Use `tax estimator` when the calculation needs a standalone name. Avoid `calculator` as the product name when the product also provides filing dates or actions, because it implies exact arithmetic and undersells the rest of the experience.

### State facts the system knows

- Prefer exact names, amounts, dates, recipients, and timing when reliable.
- Say whether an action completed, is queued, is still processing, or failed.
- Do not promise certainty the system cannot provide.
- Avoid blame. Describe the condition and recovery, not what the person “did wrong.”
- Preserve variables as structured tokens such as `{project_name}` and document fallback behavior.

## Cover the state model

For every consequential flow, inspect at least these states:

| State | Copy must answer |
| --- | --- |
| Ready | What can I do here? |
| Empty | Why is this empty, and how do I start? |
| In progress | Is the system working, and can I leave? |
| Success | What completed, for whom, and what is next? |
| Error | What happened, what was preserved, and how do I recover? |
| Blocked | Why can’t I continue, and who or what can unblock me? |
| Destructive | What disappears or changes, when, for whom, and can it be undone? |
| Partial | What succeeded, what did not, and how are retries handled? |

Add permission, offline, expired, conflict, and zero-result states when the interaction can produce them. Do not invent states the product cannot detect or actions it cannot perform.

## Handle evidence and unknowns

When given screenshots, prototypes, requirements, or code:

- Distinguish observed strings from inferred behavior.
- Flag contradictions between copy and actual behavior.
- Treat layout and control type as evidence of priority and commitment.
- Preserve product terminology unless it is misleading; propose renames explicitly rather than silently drifting.
- Mark unresolved product decisions as questions, not copy variants.
- Do not use copy to conceal a broken interaction. Recommend the smallest interaction change when words alone cannot fix it.

When researching other products, extract transferable patterns rather than assembling a collage of copied strings. Record product, platform, surface, capture date if known, observed words, and the interaction lesson.

## Deliver useful copy

Match the output to the task. For a small request, provide the final string and one sentence of rationale. For a flow or audit, use a compact copy table:

| ID / surface | State or trigger | Component | Final copy | Behavior / rationale |
| --- | --- | --- | --- | --- |

Include variable names, character constraints, plural rules, and accessibility notes only where relevant. Keep observed copy and proposed copy visually distinct.

When critiquing, use:

- **Issue:** the specific comprehension, confidence, action, or recovery problem.
- **Impact:** what the person may misunderstand or fail to do.
- **Recommendation:** the replacement copy, or the needed interaction change.

Do not offer multiple variants by default. Provide one recommended version. Add alternatives only when they represent a real product or tone tradeoff, and name that tradeoff.

## Final review

Before finishing, verify:

- A person can identify the page, object, current state, and next action.
- Primary and secondary actions cannot be confused.
- Controls describe outcomes rather than generic progression.
- Terms are audience-facing and consistent.
- Helper text adds information instead of repeating labels.
- Empty states teach one useful first move.
- Errors preserve dignity and offer a real recovery.
- Destructive copy states scope, timing, reversibility, and data consequences.
- Success copy confirms the actual result and avoids false completion.
- Text works with keyboard, screen reader, zoom, narrow screens, and translation expansion.
- Tone suits the moment; wit never competes with safety or clarity.
- Every word earns its place, and no required fact was cut for brevity.
