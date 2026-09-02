# 17 — Page Completeness Review

- **Priority:** P1
- **Size:** M (1–3 days)
- **Source:** Editing briefing, "Feature 5: Page-Level Completeness Review" section
- **Depends on:** Nothing (can be built on existing PdfViewer)
- **Blocks:** #16 (Document lifecycle — uses page status in completeness check)

## Why

After working through system detections, the reviewer needs to verify they haven't missed anything. Without page-by-page tracking, there's no way to know if page 47 of a 200-page document was actually looked at. This is a compliance requirement for thorough Woo processing.

## Scope

### Page status model

- [ ] New `page_reviews` table: `document_id`, `page_number`, `status`, `reviewer_id`, `updated_at`
- [ ] Four statuses: unreviewed (default), in_progress, complete, flagged
- [ ] Status persists immediately on change (no save action needed)

### Page status indicators

- [ ] Page strip (thumbnails or numbered circles) in PdfViewer showing status per page:
  - Unreviewed: empty circle
  - In progress: half circle
  - Complete: filled green circle with checkmark
  - Flagged: amber flag icon
- [ ] Status also visible in sidebar page navigation

### Marking pages

- [ ] "Pagina beoordeeld" (Page reviewed) button at bottom of each page or floating corner button
- [ ] Click → sets page to "complete", green checkmark appears
- [ ] "Later terugkomen" (Flag for later) option → sets to "flagged"
- [ ] Keyboard: `P` marks current page reviewed, `F` flags it (Edit Mode only)

### Progress display

- [ ] Progress text in toolbar: "12/15 pagina's beoordeeld · 3 detecties openstaand"
- [ ] Updates dynamically as pages are marked

### Auto-status

- [ ] Page automatically moves to "in_progress" when any detection on that page is reviewed

## Acceptance Criteria

- Every page has a visible status indicator
- Reviewer can mark pages as complete or flagged
- Progress shows in the toolbar
- Page statuses persist immediately to the database
- Completeness check (in #16) can query: "are all pages complete?"

## Not in Scope

- Mandatory sequential review (reviewer can mark pages in any order)
- Auto-complete when all detections on a page are resolved
