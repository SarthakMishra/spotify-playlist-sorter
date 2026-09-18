# HEY and Basecamp interface evidence

Use this reference to understand the reasoning behind the skill. It records representative observations, not a canonical or exhaustive string library. Product interfaces change; verify current copy when exact present-day wording matters.

## Contents

- Source boundaries
- Getting Real principles
- HEY patterns
- Basecamp patterns
- Transferable voice model
- Anti-patterns to avoid
- Representative sources

## Source boundaries

The principles below were derived from:

- Basecamp's [“Copywriting is Interface Design”](https://basecamp.com/gettingreal/09.7-copywriting-is-interface-design) chapter.
- Current public [HEY feature explanations](https://www.hey.com/features/) and [Basecamp feature explanations](https://basecamp.com/features).
- Representative HEY iOS and Basecamp web interface captures indexed by Mobbin.

Keep observed words separate from proposed copy. Short quoted strings below are evidence of a pattern, not text to reuse by default.

## Getting Real principles

The chapter treats decisions about labels, quantities, examples, state names, and explanatory length as interface design. Its operative lessons are:

1. Every word changes the interaction, just as an icon or layout choice does.
2. Start with what the reader needs to know in that moment.
3. Use the audience's language, not internal or technical jargon.
4. Keep copy concise and clear, but recognize that forms, buttons, instructions, policies, and examples are functional design elements.

“Short” is therefore not the goal by itself. The goal is the shortest copy that preserves the person's understanding of state, action, and consequence.

## HEY patterns

### Build a mental model with named destinations

HEY separates email into memorable, behavior-based places: “Imbox,” “The Feed,” “Paper Trail,” “Screened Out,” and “Everything.” The names are distinctive, but each novel concept receives a plain definition.

- [Paper Trail screen](https://mobbin.com/screens/6e210d14-e18e-40b4-878c-0025782fad07): the title is followed by a one-sentence definition naming receipts, confirmations, and transactional email.
- [Screened Out screen](https://mobbin.com/screens/bb58d9f1-681a-44ed-97c6-b1b85f9b105b): the copy states both which messages appear and that they are deleted after 90 days.
- [Everything screen](https://mobbin.com/screens/e045a870-07c5-4aca-adeb-66a7792e339d): the definition clarifies that sent, received, screened-out, spam, and trash are included.

Lesson: a coined name is usable when its definition, membership rules, and behavior are visible at first encounter.

### Turn classification into a human decision

The [Screener](https://mobbin.com/screens/04169699-9b3b-455e-98d4-4b315239af16) explains that these are people trying to email the person for the first time. The immediate controls are “Yes” and “No”; choosing yes reveals concrete destinations. A separate [classification prompt](https://mobbin.com/screens/002cbd9e-6966-49bf-be37-7f0b8e51e109) describes three recognizable kinds of email in first-person language: important correspondence, newsletters, and transactional mail.

Lesson: ask the question the person can answer from experience, then map that answer to system behavior. Do not ask them to understand the data model first.

### Teach one unfamiliar behavior at the moment of use

The [Feed coachmark](https://mobbin.com/screens/71696072-6788-4c79-9713-068f04f43f1c) compares newsletter flow with social feeds, explains that items are not individually archived, and ends with a simple “Next…” action.

Lesson: a concrete analogy can replace a tour, but keep it local to the current behavior and provide a clear exit.

### Name actions by the user's intention

HEY's message actions include short intention labels such as “Reply,” “Later,” and “Aside.” The public feature language expands those ideas as “Reply Later,” “Set Aside,” “Bubble Up,” and “Focus & Reply.” These names describe how a person wants to handle a message, not an email protocol operation.

Lesson: verbs can encode a workflow. Prefer a meaningful intention over generic storage actions when the product supports that intention consistently.

### Put consequence into settings and feedback

The [sender settings screen](https://mobbin.com/screens/4d7775bb-5287-4560-b58b-5bc5f75927ff) frames its first choice as “Deliver their emails to…” and its second as how to display those emails. A [saved state](https://mobbin.com/screens/e045a870-07c5-4aca-adeb-66a7792e339d) notes that changes may take a few minutes to complete.

Lesson: organize settings around what will happen, and distinguish saved input from completed processing.

## Basecamp patterns

### Use question-led forms

Basecamp often turns configuration into a series of ordinary questions.

- [Automatic Check-in form](https://mobbin.com/screens/285a5f2b-05bd-4f18-9164-d06d2838fb83): asks what question to ask, how often, at what time, who to ask, and who should see it. The action is “Start collecting answers.”
- [Invitation role step](https://mobbin.com/screens/25f84b6c-8d34-4a01-a8d8-9b68fccf89f1): asks “Who are you inviting?” and describes each option through relationship, capabilities, and limits.

Lesson: structure copy around the decisions people already understand. Finish with the real outcome, not a generic “Submit.”

### Explain choices beside the choice

The [contractor setup screen](https://mobbin.com/screens/decf8b4e-345b-4721-848e-fc41e1cdc462) explains account-level limitations above the fields and offers a personal invitation note where it is relevant. The [administrator screen](https://mobbin.com/screens/dc97154b-a2c9-49df-a8fd-162d942e653f) lists the powers that role receives before the grant action.

Lesson: capability and risk information belongs before commitment, not in documentation or a later warning.

### Make staged actions reveal the next stage

Invitation actions include labels such as “Next, enter their name…” and “Email invitation now…”. After completion, the [success screen](https://mobbin.com/screens/7605dd73-96bb-4f75-8079-be75cf86e10e) says who was emailed and offers the next setup decision—choosing visible projects—alongside an explicit postpone action.

Lesson: progression labels should reduce uncertainty about what clicking does now and what decision follows.

### Treat the blank slate as instruction

The [Message Board empty state](https://mobbin.com/screens/81058ba9-1633-4234-a12a-1c87c41bdb53) says there are no messages, then lists suitable content: announcements, pitch ideas, and feedback-gathering topics. A [new project state](https://mobbin.com/screens/f5e07e02-5e13-4f39-9e25-81bc3ab7be2e) suggests a message, to-dos, a document, a reference point, a calendar event, or a person.

Lesson: the empty state should teach the feature's purpose through realistic first moves, not announce absence alone.

### Make destructive consequences inspectable

The [account cancellation screen](https://mobbin.com/screens/a7702d8d-d6fe-4e9a-b7e2-be87f2277f24) distinguishes immediate account closure from later deletion windows, offers export before cancellation, links to support, and uses a specific destructive action. The [merge-people confirmation](https://mobbin.com/screens/e0b8288f-3acf-435e-b24b-ba36fdfda53a) itemizes what access and history do or do not move and states that the action cannot be undone.

Lesson: “Are you sure?” is not enough. Name asymmetric effects, timing, recovery, and the exact commitment.

### Connect labels with small functional descriptions

On the [project tool chooser](https://mobbin.com/screens/4534b2ef-f4b0-49a8-8f58-75b022cc1b5b), tools such as Message Board, To-dos, Docs & Files, Calendar, and Chat receive concise descriptions of what belongs there. The description distinguishes similar tools without forcing the person to open each one.

Lesson: a short noun-plus-purpose pair can do more work than a clever label or a separate help page.

## Transferable voice model

The shared voice can be modeled without imitation:

| Quality | Operational behavior |
| --- | --- |
| Direct | Lead with the question, state, or outcome. |
| Concrete | Name the object, person, timing, and example. |
| Human | Use ordinary relationship words and natural questions. |
| Opinionated | Recommend a mental model rather than exposing implementation options. |
| Explanatory | Teach novelty and consequence next to the control. |
| Calm | Use plain facts for errors, risk, and routine success. |
| Economical | Stop when the knowledge gap is closed. |

Adapt these behaviors to the product's audience. A banking, medical, developer, children's, or government interface will need different terminology and degrees of warmth.

## Anti-patterns to avoid

- Do not copy 37signals' jokes, contractions, ellipses, or coined nouns merely to sound distinctive.
- Do not invent a branded vocabulary for ordinary objects.
- Do not turn every heading into a conversational question; use it when the screen is truly a decision.
- Do not lengthen every choice into a paragraph. Explain only meaningful differences.
- Do not use friendly tone to soften or obscure data loss, payment, permission, or legal effect.
- Do not assume captured interface copy is current, universally successful, or appropriate for another domain.
- Do not treat public marketing language as interchangeable with in-product instructions.

## Representative sources

Official sources:

- [Copywriting is Interface Design](https://basecamp.com/gettingreal/09.7-copywriting-is-interface-design)
- [HEY features](https://www.hey.com/features/)
- [Basecamp features](https://basecamp.com/features)

Representative HEY interface captures:

- [The Screener](https://mobbin.com/screens/04169699-9b3b-455e-98d4-4b315239af16)
- [Paper Trail](https://mobbin.com/screens/6e210d14-e18e-40b4-878c-0025782fad07)
- [The Feed education](https://mobbin.com/screens/71696072-6788-4c79-9713-068f04f43f1c)
- [Message classification](https://mobbin.com/screens/002cbd9e-6966-49bf-be37-7f0b8e51e109)
- [Sender settings](https://mobbin.com/screens/4d7775bb-5287-4560-b58b-5bc5f75927ff)

Representative Basecamp interface captures:

- [Project tool chooser](https://mobbin.com/screens/4534b2ef-f4b0-49a8-8f58-75b022cc1b5b)
- [Message Board empty state](https://mobbin.com/screens/81058ba9-1633-4234-a12a-1c87c41bdb53)
- [Invitation role choice](https://mobbin.com/screens/25f84b6c-8d34-4a01-a8d8-9b68fccf89f1)
- [Invitation success](https://mobbin.com/screens/7605dd73-96bb-4f75-8079-be75cf86e10e)
- [Automatic Check-in form](https://mobbin.com/screens/285a5f2b-05bd-4f18-9164-d06d2838fb83)
- [Account cancellation](https://mobbin.com/screens/a7702d8d-d6fe-4e9a-b7e2-be87f2277f24)
- [Merge confirmation](https://mobbin.com/screens/e0b8288f-3acf-435e-b24b-ba36fdfda53a)
