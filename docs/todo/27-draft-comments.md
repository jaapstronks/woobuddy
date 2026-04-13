# 27 — Draft Comments

- **Priority:** P3
- **Size:** M (1–3 days)
- **Source:** Draft Workflow briefing, "Draft annotations" section
- **Depends on:** #26 (Draft preview), #32 (Auth)
- **Blocks:** Nothing

## Why

Supports the common workflow where a jurist reviews the draft and leaves notes without directly modifying decisions. Lighter than a full review round-trip — the jurist doesn't need to understand the detection system.

**Client-first note:** Comments are stored server-side as text written by the commenter (not extracted from the document), so they don't violate the client-first principle. They reference detections by ID, not by quoting sensitive text. The jurist must have the PDF loaded in their browser to see what they're commenting on.

## Scope

### Comment creation

- [ ] Click on a redacted area in draft preview → comment field appears
- [ ] Comments stored in `draft_comments` table: `detection_id`, `document_id`, `author_id`, `text`, `status` (open/resolved), timestamps. Comment text is authored by the commenter (not extracted from the document), so it's acceptable to store server-side. However, commenters should be advised not to quote sensitive text verbatim in their comments.

### Display

- [ ] Small indicator icons on redacted areas that have comments
- [ ] Expandable on click to show comment text and author
- [ ] Resolved comments show as faded/strikethrough

### Resolution

- [ ] Original reviewer sees comments on next visit
- [ ] Can resolve by adjusting the redaction or marking as "afgehandeld"
- [ ] Unresolved comments block document approval (in #25 completeness check)

## Acceptance Criteria

- Jurist can add comments on specific redactions in the draft preview
- Reviewer sees and can resolve comments
- Unresolved comments block approval

## Not in Scope

- Threaded replies (single comment per detection, not a conversation)
- Comment notifications (email alerts for new comments)
- @mentions
