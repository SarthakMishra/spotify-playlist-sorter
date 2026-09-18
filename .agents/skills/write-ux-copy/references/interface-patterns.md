# Interface copy pattern library

Use this reference to draft or review a specific surface. The examples are original and illustrative; adapt nouns, policy, behavior, and tone to the actual product.

## Contents

- Navigation, names, and headings
- Buttons and links
- Forms and input guidance
- Empty, first-run, and zero-result states
- Onboarding and just-in-time education
- Success, status, and progress
- Validation and errors
- Confirmations and destructive actions
- Permissions, privacy, and security
- Settings and preferences
- Search, filters, sorting, and tables
- Notifications and subscriptions
- Loading, offline, expired, and conflict states
- Invitations, roles, and admin controls
- Account, billing, and upgrade flows
- Data-heavy and professional interfaces
- AI and automation interfaces
- Accessibility, localization, and variables
- Product-wide copy audits

## Navigation, names, and headings

Names create the product's mental model. Use familiar nouns by default. Introduce a branded term only when it names a distinct, repeatable concept and the interface can define it where first encountered.

- Navigation labels identify destinations: nouns such as “Projects” or “Payments.”
- Action labels change state: verbs such as “Create project” or “Record payment.”
- Page titles identify the place or object. They need not repeat the global navigation label.
- Question headings work well when the page is a single decision.
- Section headings should help scanning, not merely divide whitespace.

Bad: `Management Center`

Good: `Team members`

Bad: `Configure`

Good: `Who can see this project?`

Bad: `Data object overview`

Good: `Invoice INV-1042`

## Buttons and links

A button should complete the sentence “I want to …” and predict the immediate outcome.

| Situation | Bad | Good |
| --- | --- | --- |
| Create | Submit | Create project |
| Save edits | Update | Save changes |
| Send | Confirm | Send invitation |
| Export | Proceed | Download CSV |
| Delete | Yes | Delete invoice |
| Next decision | Continue | Next: choose a plan |
| Delay | Later | Remind me tomorrow |

Use “Save” only when the object already exists and the meaningful outcome is persistence. Use “Create,” “Send,” “Publish,” “Start,” “Schedule,” or “Pay” when those outcomes matter more.

Use links for navigation, disclosure, or low-commitment secondary actions. Write them as actions when they act: “View calculation,” “Change recipient,” “Learn how tax is estimated.” Avoid “Click here” and vague “Learn more” when the topic fits.

Keep cancel actions contextual:

- `Never mind` suits a reversible dialog with no changes committed.
- `Cancel` suits an in-progress edit whose cancellation is already understood.
- `Keep editing` is safer when closing would discard work.
- `Not now` is valid only when the task can genuinely wait; add timing if useful.

## Forms and input guidance

Use visible labels. A placeholder is an example or format hint, not a replacement label.

Form sequence:

1. Ask a human question or name the requested fact.
2. Explain why it is needed only when unclear.
3. Show format or constraints before entry.
4. Validate near the field.
5. Label the final action with its outcome.

Bad label: `Identifier`

Good label: `GSTIN`

Good helper text: `15 characters, for example 22AAAAA0000A1Z5.`

Bad helper text: `Enter your GSTIN here.`

Good helper text: `We’ll use this GSTIN on tax invoices.`

Bad placeholder: `Name`

Good label: `Client name`

Good placeholder: `Acme Pvt Ltd`

For optional fields, mark the label `(optional)` instead of explaining absence as an error. Do not mark every required field if nearly all are required; explain once at the form level when necessary.

For complex choices, describe differences in capability or consequence:

Bad:

- `Standard user`
- `External user`
- `Restricted user`

Good:

- `Team member — can create projects and invite people`
- `Contractor — can work in assigned projects only`
- `Client — can view selected project areas`

Do not hide a policy in an error that appears only after submission.

## Empty, first-run, and zero-result states

An empty state is the first page of the feature, not an apology. Distinguish:

- **First-run empty:** nothing exists yet; teach the purpose and first action.
- **User-cleared empty:** acknowledge completion; do not re-onboard.
- **Filtered empty:** explain that filters hide results and offer to clear them.
- **Search zero:** echo the query and suggest a specific recovery.
- **Permission empty:** do not imply there is no data if the person cannot see it.
- **Error empty:** never disguise a failed load as “nothing here.”

Bad: `No data.`

Good: `No projects yet`

`Create a project to keep its messages, tasks, files, and dates together.`

`Create project`

Bad: `Nothing found.`

Good: `No invoices match “April retainer”`

`Try a different term or clear the date filter.`

`Clear filters`

For a completed queue, prefer calm confirmation:

Good: `You’re all caught up.`

Do not add a primary action when there is no useful next step.

## Onboarding and just-in-time education

Teach the smallest concept needed for the current decision. Prefer a concrete analogy or example over a tour of every feature.

Effective sequence:

1. Name the new concept.
2. Connect it to something familiar.
3. Explain the immediate behavior.
4. Let the person try it.

Bad: `Welcome to our revolutionary workflow engine. Let’s explore eight powerful capabilities.`

Good: `Keep receipts out of your main inbox`

`Send order confirmations and receipts to Paperwork. They’ll stay searchable without crowding important messages.`

`Choose a sender`

Use examples drawn from the person's likely work. Do not use setup screens as disguised marketing. Allow skipping when the lesson is not required for safe use, and make skipped education discoverable later.

## Success, status, and progress

Success copy should confirm what the system actually completed. Use the object and recipient when useful.

Bad: `Success!`

Good: `Invitation emailed to Priya Shah.`

Bad: `Done.`

Good: `Payment recorded on invoice INV-1042.`

If work is asynchronous, distinguish acceptance from completion:

Bad: `Import complete.`

Good: `Import started. You can leave this page; we’ll notify you when 842 transactions are ready.`

For partial success:

Good: `18 of 20 invoices sent`

`Two invoices are missing customer email addresses.`

`Review unsent invoices`

Avoid congratulatory noise for routine saves. A quiet `Changes saved` is often enough. If completion may take time, say so without pretending the state is final.

## Validation and errors

An error should say:

1. What could not happen.
2. Why, if known and useful.
3. What was preserved.
4. How to recover.

Do not blame the person, expose internal codes, or suggest an action that cannot help.

Bad: `Invalid input.`

Good: `Enter a date on or after 1 April 2026.`

Bad: `Something went wrong. Try again.`

Good: `We couldn’t save this invoice because the connection was lost. Your changes are still here. Reconnect and try again.`

Bad: `User not authorized.`

Good: `You can view this report, but only account owners can change its settings.`

Use field errors for field problems, a banner for page-level problems, and a dialog only when work must stop. Preserve entered data wherever possible and say when it was not preserved.

Do not invent a cause. If unknown, be honest and offer a meaningful next move:

Good: `We couldn’t upload “receipts.zip”. Try again, or upload files individually.`

## Confirmations and destructive actions

Ask for confirmation only when the action is hard to reverse, surprising, unusually broad, or costly. Prefer undo for ordinary, reversible actions.

A destructive confirmation should include:

- the exact action and object;
- affected people, access, money, or data;
- timing and retention;
- reversibility and available recovery;
- a specific destructive button;
- a safe secondary action.

Bad:

`Are you sure?`

`This action cannot be undone.`

`Yes / No`

Good:

`Delete “Q2 planning”?`

`The project and its 14 files will move to Trash for 30 days. Team members will lose access now.`

`Delete project / Keep project`

For irreversible merges or transfers, itemize asymmetric consequences rather than relying on “cannot be undone.”

Good:

`Merge Arun into A. Kumar?`

- `Arun’s assignments and project access will move to A. Kumar.`
- `Arun’s private messages will not move.`
- `Arun will be removed from the account.`

`Merge people / Never mind`

Avoid softened destructive verbs such as “Deactivate” when data is deleted. Avoid frightening language for routine revocable actions.

## Permissions, privacy, and security

Permissions need a purpose, scope, and fallback—not coercion.

Bad: `Allow contacts access to continue.`

Good: `Find teammates in your contacts`

`We’ll compare email addresses to suggest people you know. We won’t message anyone.`

`Allow contacts / Enter email instead`

For authorization failures, distinguish role, ownership, subscription, and authentication problems. Name who can unblock the action.

Bad: `Access denied.`

Good: `Only workspace owners can export all customer data. Ask Maya or Rohan to export it.`

For security events, state observed facts and protective action. Do not imply compromise without evidence.

Good: `We signed you out because your password changed. Sign in again to continue.`

## Settings and preferences

Write settings around behavior and consequence. A toggle label must make sense with its current value and should not require interpreting a double negative.

Bad: `Disable non-priority notifications`

Good: `Notify me about priority messages only`

Add helper text when the boundary is not obvious:

Good label: `Bundle messages from this sender`

Good helper: `New messages will appear in one row. Nothing is deleted.`

For grouped settings, use question or outcome headings:

- `Where should these messages go?`
- `Who should be notified?`
- `When should this repeat?`

When a change is delayed, say so: `Changes saved. New permissions may take a few minutes to apply.`

## Search, filters, sorting, and tables

Use the object's plural noun in search fields: `Search invoices`, not `Search`. Name filters by the property they change: `Status`, `Owner`, `Date range`.

Reflect active constraints in the zero state and make reversal easy:

Good: `No overdue invoices assigned to you.`

`Clear “Assigned to me”`

Use column headings that describe values, not database fields. Include units in headings when every value shares them: `Amount (INR)`. Put action menus under an accessible label such as `Actions for invoice INV-1042`, even if the visible control is an icon.

Avoid using copy to compensate for an overloaded table. If people need paragraphs to understand each column, recommend progressive detail or a summary view.

## Notifications and subscriptions

Answer: what triggers the notification, which channel is used, how often, and who receives it.

Bad: `Notifications: On`

Good: `Email me when someone comments on this proposal.`

Bad: `Notify users`

Good: `When I publish this, notify…`

`Everyone following the project / Selected people / No one`

Differentiate a notification preference from an action's recipients. Never silently subscribe someone because they viewed a page.

## Loading, offline, expired, and conflict states

Use specific progress when measurable. Otherwise name the work, not generic waiting.

Bad: `Loading…`

Good: `Preparing 842 transactions…`

Do not promise a duration unless reliable. Say whether the person can navigate away.

Offline:

Good: `You’re offline. Your draft is saved on this device and will send when you reconnect.`

Expired:

Good: `This invitation expired on 2 September. Ask the project owner for a new one.`

Conflict:

Good: `Meera saved a newer version while you were editing.`

`Review her changes / Keep my version`

State whether retrying may duplicate an action, especially for payments, messages, and imports.

## Invitations, roles, and admin controls

Describe roles by capabilities and limits rather than rank alone. Use real relationship terms—team member, contractor, client—when those align with permissions.

Bad: `Select user type.`

Good: `Who are you inviting?`

Bad option: `External`

Good option: `Client — can view selected projects but can’t create new ones.`

After an invitation, confirm delivery and offer the next setup task:

Good: `Invitation emailed to Jane Doe.`

`Choose the projects Jane can see / I’ll do this later`

Be explicit when an invitation grants account-wide access, incurs a seat charge, or exposes existing content.

## Account, billing, and upgrade flows

State prices, billing period, taxes if known, renewal date, proration behavior, trial effect, and cancellation consequence close to the commitment.

Bad: `Upgrade now`

Good: `Start Pro for ₹1,499/month`

Bad: `Your account will be downgraded.`

Good: `Your Pro plan ends on 30 September. After that, automations will stop and your existing data will remain available.`

Cancellation copy should be humane but factual. Provide export or migration options before deletion. Do not create artificial urgency or hide a secondary exit.

## Data-heavy and professional interfaces

Optimize for scanability, exactness, and auditability.

- Use established domain terms; define uncommon abbreviations once.
- Put period, currency, tax basis, timezone, and status near the number they qualify.
- Distinguish estimates, reported values, pending values, and final values.
- Explain calculations through inspectable inputs, not vague assurances.
- Never collapse uncertainty into a confident action label.

Bad: `Tax due: ₹24,310`

Good: `Estimated tax due for FY 2026–27: ₹24,310`

`Based on income and credits entered through 3 September.`

`View calculation`

Bad: `Delete entry`

Good: `Void journal entry` when the accounting system preserves an audit trail; use `Delete draft entry` only when it truly removes an unposted draft.

## AI and automation interfaces

Make agency, inputs, output status, and review responsibility explicit.

Name the action precisely:

- `Draft reply` if the system creates editable text.
- `Summarize this thread` if it produces a summary.
- `Send automatically` only if it will act without review.

Bad: `Ask AI`

Good: `Draft a response from this thread`

Bad success: `Done.`

Good success: `Draft ready. Review names, dates, and amounts before sending.`

For tool-using agents, state what they can access and when approval is required. Distinguish a suggestion from an executed action. Show sources for factual claims when available, and never use confident tone as a substitute for evidence.

## Accessibility, localization, and variables

- Do not rely on icon, color, direction, position, or punctuation alone.
- Give icon-only controls accessible names that include their object when repeated.
- Keep link text meaningful out of context.
- Use plain sentence structure that survives translation.
- Avoid assembling sentences from fragments; word order and pluralization vary.
- Allow expansion in controls and navigation.
- Format dates, times, numbers, currency, and names by locale.
- Never assume English name order, binary gender, or a single grammatical plural.

Document variables with examples and fallbacks:

`Invitation emailed to {recipient_name}.`

- If name is absent, use the email address.
- If multiple recipients exist, use a localized count rather than joining an unbounded list.
- Escape user-provided text and preserve the UI's truncation behavior.

## Product-wide copy audits

Create an inventory by object and state, then look for system problems:

1. Multiple names for the same object.
2. One name used for different objects.
3. Generic action labels with different outcomes.
4. Missing empty, failure, permission, partial, or destructive states.
5. Explanations far from the choice they qualify.
6. Tone that becomes playful at high-stakes moments.
7. Copy that promises behavior the product does not implement.
8. Backend language leaking into the interface.
9. Repeated helper text that adds no information.
10. Unspecified variables, plural rules, truncation, or localization.

Recommend changes in terms of comprehension, confidence, action, recovery, and operational risk. Prioritize by severity and frequency, not by stylistic preference.
