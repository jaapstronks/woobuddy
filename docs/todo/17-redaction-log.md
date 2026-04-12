# 18 — Redaction Log

- **Priority:** P2
- **Size:** L (3–7 days)
- **Source:** Draft Workflow briefing, "The Redaction Log" section
- **Depends on:** #00 (Client-first architecture — log cannot contain entity text), #24 (Auth), #25 (Organizations)
- **Blocks:** Nothing

## Why

The review sidebar is optimized for making decisions one at a time. The redaction log is a different tool: a table view for oversight, consistency checking, and bulk revision. Think code editor vs pull request review — different activity, different UI. Supervisors and jurists need the log view to efficiently check all decisions across a dossier.

**Client-first impact:** The log cannot show the actual redacted text (entity_text) since the server doesn't store it. Instead, the log shows entity type, tier, article, page, position, reviewer, and status. To see the actual text, the user clicks "Bekijk in document" which opens the PDF (from their browser) at the right page. This is a deliberate tradeoff: less context in the log table, but zero sensitive text on the server.

## Scope

### Routes

- [ ] `/app/dossier/[id]/log` — dossier-level log (primary view)
- [ ] Per-document log accessible from document detail page (filtered subset)

### Log table (no entity text — client-first)

- [ ] Columns: #, Document (dossier view), Page, **Type** (entity type badge — replaces "Passage" column since entity text is not stored server-side), Tier, Article, Status, Source, Reviewer, Date, Motivation (generic article template)
- [ ] **"Bekijk" (View) button** per row — opens the document review at the detection's page so the user can see the actual text in context (from their local PDF)
- [ ] If the user has the PDF open in their browser, the log can optionally show entity text by doing a client-side join (match detection bbox against locally extracted text)
- [ ] Sortable columns: #, Document, Page, Tier, Article, Reviewer, Date
- [ ] Filterable columns: Document, Page, Type, Tier, Article, Status, Source, Reviewer
- [ ] Compound filters (multiple active at once)
- [ ] Grouping: by article, by document, by status, by reviewer

### Detail panel

- [ ] Click a row → slide-in panel (or expandable row)
- [ ] Shows: detection metadata (type, tier, article, confidence, source), motivation text, action buttons (accept/reject/defer/edit)
- [ ] If the PDF is loaded in the browser, shows the passage text via client-side bbox lookup against local text
- [ ] "Bekijk in document" link → navigates to review interface at the right page (primary way to see full context)

### Batch operations

- [ ] Multi-select via checkboxes
- [ ] Bulk status change, bulk article change, bulk delete (manual detections only)
- [ ] All batch ops require confirmation showing what will change and how many items

### Statistics bar

- [ ] Top of log: total counts by status, by article, manual vs auto
- [ ] Updates dynamically when filters change

### Performance

- [ ] Server-side filtering/sorting via query parameters
- [ ] Paginated results (not all rows at once)
- [ ] Virtual scrolling for large result sets (5000+ detections)

### API endpoints

- [ ] `GET /api/dossiers/:id/log` — filterable, sortable, paginated
- [ ] `GET /api/documents/:id/log` — same, scoped to one document
- [ ] `GET /api/documents/:id/log/stats` — statistics for the current filter

## Acceptance Criteria

- Dossier-level log shows all detections across all documents
- Filters compound correctly (e.g., article + status + reviewer)
- Clicking a row shows detail with action buttons
- Batch status change works and requires confirmation
- Statistics bar reflects current filter

## Not in Scope

- Storing entity text server-side to populate the Passage column (violates client-first architecture)
- Export the log itself as a spreadsheet (see #23 for redaction inventory)
- Real-time updates (log refreshes on navigation, not live)
