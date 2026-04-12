# WOO Buddy — Supplementary Briefing: Redaction Log, Draft Workflow & Re-Export

## Context

The main briefing describes detection and review as a forward-moving pipeline: upload → detect → review → export. But in real Woo practice, the process is iterative. A reviewer works through a document, makes redaction decisions, then a colleague or jurist reviews the result. They disagree with some decisions. Or the reviewer themselves realizes after seeing the full picture that they were too aggressive or too lenient. Or new information comes in — a person who was classified as a private citizen turns out to be a public official, and twenty redactions across the dossier need to be reversed.

The redacted document must be a **living draft** — reviewable, modifiable, re-exportable — until the moment it is formally finalized as part of the Woo decision. This briefing covers three interconnected features:

1. **The Redaction Log** — a structured, sortable, filterable list of every redaction decision on a document or dossier
2. **The Draft Workflow** — treating the redacted document as a work-in-progress that can be iterated on
3. **Re-Export** — generating updated redacted PDFs and motivation reports after changes

---

## The Redaction Log

### What it is

A **table view** of every redaction decision made on a document (or across an entire dossier), showing what was redacted, why, by whom, and when. This is distinct from the review interface's sidebar, which is optimized for making decisions one at a time. The log is optimized for **oversight, consistency checking, and bulk revision**.

Think of it as the difference between writing code (the review interface) and reviewing a pull request (the log). Different activity, different UI, different mental mode.

### Where it lives

New route: `/app/dossier/[id]/log` (dossier-level) and accessible per-document from the document detail page.

The dossier-level log is the more important view — a Woo decision covers all documents in the dossier, and the reviewer or their supervisor needs to see the full picture. The per-document view is a filtered subset.

### Log table structure

Each row represents one detection/redaction decision. Columns:

| Column | Content | Sortable | Filterable |
|--------|---------|----------|------------|
| **#** | Sequential number within the document | ✓ | — |
| **Document** | Filename (dossier-level view only) | ✓ | ✓ |
| **Page** | Page number | ✓ | ✓ |
| **Passage** | The redacted text, truncated to ~60 chars with full text on hover. For area redactions: "[Afbeelding/gebied]" | — | ✓ (search) |
| **Type** | Entity type badge: persoon, BSN, telefoon, etc. For Tier 3: "beleidsopvatting", "bedrijfsgegeven", etc. | — | ✓ |
| **Tier** | 1, 2, or 3 | ✓ | ✓ |
| **Article** | Woo article code: 5.1.1e, 5.1.2e, 5.2, etc. | ✓ | ✓ |
| **Status** | Current decision: gelakt (redacted), niet gelakt (kept), uitgesteld (deferred), concept (draft, no decision yet) | — | ✓ |
| **Source** | How it was detected: auto, NER, LLM, handmatig (manual), zoek & lak (search-and-redact) | — | ✓ |
| **Beoordelaar** | Who made the decision | ✓ | ✓ |
| **Datum** | When the decision was made | ✓ | — |
| **Motivering** | Truncated motivation text, full on hover/click | — | ✓ (search) |

### Interaction from the log

Each row is clickable. Clicking a row opens a **detail panel** (slide-in from the right, or expandable row — not a full page navigation) showing:

- The full passage text with surrounding context (±200 chars)
- The full motivation text
- The detection source and confidence level
- **Action buttons**: the same accept/reject/defer/edit controls as the review sidebar
- A **"Bekijk in document" (View in document)** link that navigates to the review interface, scrolled to this detection on the correct page

This means the reviewer can make changes directly from the log without switching to the full review interface. This is critical for the "supervisor reviews all decisions" workflow — the supervisor scans the log, spots something questionable, clicks the row, reads the context, changes the decision, moves on.

### Log-level batch operations

The log supports **multi-select** (checkboxes on each row) with batch actions:

- **Bulk status change**: select 15 detections → change all from "gelakt" to "niet gelakt" (with a single article/motivation that applies to all)
- **Bulk article change**: select detections → change the Woo article on all of them (e.g., reclassify from 5.1.2e to 5.1.1d)
- **Bulk reassign**: select detections → assign to a different reviewer for re-evaluation
- **Bulk delete**: remove manual detections that were added by mistake

All batch operations require a confirmation step showing exactly what will change and how many items are affected.

### Filtering and grouping

The log's filter bar should support **compound filters** — multiple filters active at once:

- "Show me all detections on article 5.1.2e that are still deferred" → article filter + status filter
- "Show me everything reviewer X decided on document Y" → reviewer filter + document filter
- "Show me all manual additions across the dossier" → source filter

Additionally, the log can be **grouped by**:

- **Article** — shows all 5.1.1e decisions together, then all 5.1.2e, etc. This is useful for writing the bundled motivation per article in the Woo decision.
- **Document** — default grouping for dossier-level view
- **Status** — groups by gelakt / niet gelakt / uitgesteld / concept
- **Reviewer** — shows each person's decisions, useful for workload balancing

### Statistics bar

At the top of the log, a compact **statistics bar** summarizing the current view:

```
Totaal: 347 detecties · Gelakt: 281 · Niet gelakt: 42 · Uitgesteld: 18 · Concept: 6
Art. 5.1.1e: 34 · Art. 5.1.2e: 198 · Art. 5.2: 31 · Overig: 84
Handmatig toegevoegd: 23 · Auto-detectie: 324
```

These numbers update dynamically when filters are applied — if you filter to a single document, you see that document's stats.

---

## The Draft Workflow

### Core concept: nothing is final until you say so

Every document goes through a lifecycle:

```
uploaded → processing → review → draft → approved → exported
```

The new state is **draft**. A document enters "draft" when the reviewer has worked through all detections and pages, but the result has not yet been formally approved. In this state:

- A **preview of the redacted PDF** is available — the document rendered with black bars in place, article codes visible, exactly as it would look after export
- But the underlying data is still fully editable — any detection can still be changed, added, or removed
- The preview regenerates on every change (or on explicit refresh, depending on performance)

### Draft preview

New component: `<DraftPreview>` — renders the document with redactions applied visually but not permanently. Implementation:

- Render the PDF page via pdf.js (same as the review interface)
- Overlay black rectangles at the coordinates of all accepted/auto-accepted detections
- Render the article code as white text on each black rectangle
- This is a **client-side visual overlay**, not a server-generated PDF — it's instant and updates in real time as decisions change

The draft preview is available:

- As a **tab** on the document review page: `[Beoordelen] [Concept bekijken]` — switch between the detection review view and the draft preview
- As a **full-page view** at `/app/dossier/[id]/draft/[docId]` for colleagues/supervisors who just want to see the result without the review controls

### Side-by-side mode

For thorough review, offer a **split-screen view**: original document on the left, draft preview on the right. Both scrolled and zoomed in sync. This lets the reviewer (or their supervisor) see exactly what's being hidden and whether the result makes sense.

Toggle: `[Enkel] [Naast elkaar]` in the toolbar. On narrow screens, this falls back to a tab toggle.

### Draft annotations

In the draft preview, the reviewer or supervisor can **add comments** to specific redactions without changing them. This supports the common workflow where a jurist reviews the draft and leaves notes like "Overweeg om deze passage niet te lakken — het betreft een feitelijke constatering" without directly modifying the decision.

- Click on a redacted area in the draft preview → a comment field appears
- Comments are stored in a `draft_comments` table (detection_id, author, text, timestamp)
- Comments appear as small indicator icons on the redacted area, expandable on click
- The original reviewer sees the comments the next time they open the document, and can resolve them by adjusting the redaction or marking the comment as "afgehandeld" (resolved)

This is lighter than a full review round-trip. The jurist doesn't need to understand the three-tier system or the detection interface — they just look at the redacted document and leave notes on anything they disagree with.

### Document-level approval

When the reviewer is satisfied with the draft:

1. Click **"Goedkeuren" (Approve)** on the document
2. The system runs a **completeness check**:
   - All pages marked as reviewed?
   - All Tier 2 detections resolved (no "concept" status remaining)?
   - All Tier 3 annotations resolved?
   - All draft comments resolved?
   - Five-year rule warnings acknowledged?
3. If checks pass: status moves to "approved", the document becomes read-only (no more edits without explicit "reopen")
4. If checks fail: a dialog lists exactly what's still open, with links to each item

### Reopening an approved document

An approved document can be **reopened** for further editing. This is a deliberate action:

1. Click **"Heropenen" (Reopen)** on an approved document
2. Confirmation dialog: "Dit document is goedgekeurd. Wil je het heropenen voor verdere bewerking? Het moet opnieuw worden goedgekeurd na wijzigingen." (This document is approved. Do you want to reopen it for further editing? It will need to be re-approved after changes.)
3. Status reverts to "draft"
4. Audit log records the reopen: who, when, why (optional reason field)

---

## Re-Export

### When to export

Export is available at any time for draft or approved documents, but with clear visual distinction:

- **Draft export**: labeled "Concept-export" with a watermark or visual indicator that this is not the final version. The exported PDF includes a subtle header/footer: "CONCEPT — Niet definitief" on each page. This prevents accidental publication of draft redactions.
- **Final export**: available only for approved documents. Clean redacted PDF, no watermark. This is the version that goes into the formal Woo decision.

### What gets exported

Per document:
- **Redacted PDF** — original document with redactions permanently applied (PyMuPDF `apply_redactions()`). Article codes visible on each black bar. Configurable redaction color per ground.
- **Redaction map** — a companion PDF showing the original document with colored overlays instead of black bars, annotated with detection IDs and article codes. This is an internal reference document, not for publication. Useful for audit and for the reviewer to verify the redaction was applied correctly.

Per dossier:
- **ZIP archive** containing all redacted PDFs
- **Motivation report** (as described in the main briefing) — the structured appendix for the Woo decision, generated from all accepted redaction decisions and their motivation texts
- **Redaction inventory** — a spreadsheet (CSV or XLSX) listing every redaction: document, page, passage text, article, motivation, reviewer, date. This is the machine-readable version of the log.

### Re-export after changes

When a document is reopened and modified, the previous export becomes stale. The system must:

1. **Invalidate the previous export** — mark it as outdated in the database. If someone tries to download the old export, show a warning: "Er is een nieuwere versie beschikbaar."
2. **Track export versions** — each export gets a version number (v1, v2, v3...) and a timestamp. The system stores references to all versions, not just the latest.
3. **Diff between versions** — when a re-export is generated, optionally produce a **change summary**: "Versie 2: 3 lakkingen toegevoegd, 7 lakkingen verwijderd, 2 lakkingen aangepast ten opzichte van versie 1." This is stored in the audit log and optionally included in the motivation report.

### Export generation

Exports are generated server-side (FastAPI background task). The flow:

1. Reviewer clicks "Exporteren" (on a document or dossier)
2. System shows export options:
   - Format: concept (with watermark) or definitief (clean, only for approved documents)
   - Include: redacted PDFs, redaction map, motivation report, redaction inventory (checkboxes)
   - Redaction color: dropdown (zwart, paars, geel, or custom per article)
3. Export job starts in the background
4. Progress indicator in the UI (Shoelace `<sl-progress-bar>`)
5. When complete: download button appears, and the export is stored in MinIO with its version number

For large dossiers (100+ documents), export can take minutes. The job runs asynchronously (Celery in production, synchronous in prototype). The reviewer can navigate away and come back — the export status persists.

---

## Revised Document Lifecycle

Combining the main briefing and this supplement, the full lifecycle:

```
uploaded
  → processing (detection pipeline running)
    → review (reviewer working through detections)
      → draft (all detections addressed, preview available)
        → approved (completeness checks passed, read-only)
          → exported (final PDF generated)

At any point after "review":
  - Can generate concept-export (with watermark)
  
From "approved":
  - Can reopen → returns to "draft"
  
From "exported":
  - Can reopen → returns to "draft" (invalidates previous export)
```

---

## Database Changes

New tables:

- **`draft_comments`** — comments on specific detections from the draft review (detection_id, document_id, author, text, status: open/resolved, created_at, resolved_at, resolved_by)
- **`exports`** — export records (dossier_id, document_id [null for dossier-level], version, format: concept/definitief, storage_key in MinIO, includes: JSON array of what was included, created_at, created_by, is_current: boolean)

Modified tables:

- **`documents`** — add `current_export_id` (FK to exports), extend status enum with `draft`

---

## API Endpoints (additions)

```
GET    /api/dossiers/:id/log                 Redaction log (dossier-level, filterable)
GET    /api/documents/:id/log                Redaction log (document-level)
GET    /api/documents/:id/log/stats          Statistics for the log view

POST   /api/documents/:id/approve            Approve document (runs completeness checks)
POST   /api/documents/:id/reopen             Reopen approved document

POST   /api/detections/:id/comments          Add draft comment
GET    /api/detections/:id/comments          List comments on a detection
PATCH  /api/comments/:id                     Resolve/update a comment

POST   /api/documents/:id/export             Generate document export
POST   /api/dossiers/:id/export              Generate dossier export
GET    /api/exports/:id/status               Export job status
GET    /api/exports/:id/download             Download export
GET    /api/documents/:id/exports            List all export versions for a document
GET    /api/dossiers/:id/exports             List all export versions for a dossier
```

---

## New Frontend Components

| Component | Purpose |
|-----------|---------|
| `<RedactionLog>` | The main log table with sorting, filtering, grouping, multi-select |
| `<LogDetailPanel>` | Slide-in detail view for a single detection from the log |
| `<LogFilters>` | Compound filter bar for the log |
| `<LogStats>` | Statistics summary bar |
| `<DraftPreview>` | Document rendered with visual-only redaction overlays |
| `<SideBySide>` | Split-screen: original + draft preview, synced scroll/zoom |
| `<DraftComment>` | Comment bubble on a redacted area in draft preview |
| `<CommentThread>` | List of comments on a detection with resolve action |
| `<ExportDialog>` | Export options: format, includes, redaction color |
| `<ExportHistory>` | List of export versions with download links and change summaries |
| `<CompletenessCheck>` | Dialog showing what's still open before approval |
| `<DocumentLifecycle>` | Visual status indicator showing where the document is in its lifecycle |

---

## Project Structure (additions)

```
frontend/src/lib/components/
├── log/
│   ├── RedactionLog.svelte
│   ├── LogDetailPanel.svelte
│   ├── LogFilters.svelte
│   └── LogStats.svelte
├── draft/
│   ├── DraftPreview.svelte
│   ├── SideBySide.svelte
│   ├── DraftComment.svelte
│   └── CommentThread.svelte
├── export/
│   ├── ExportDialog.svelte
│   ├── ExportHistory.svelte
│   └── MotivationReport.svelte      (already in main briefing)
└── shared/
    ├── CompletenessCheck.svelte
    └── DocumentLifecycle.svelte

frontend/src/routes/app/dossier/[id]/
├── log/+page.svelte                  Dossier-level redaction log
└── draft/[docId]/+page.svelte        Full-page draft preview

backend/app/api/
├── log.py                            Log query endpoints
├── approval.py                       Approve/reopen endpoints
├── comments.py                       Draft comment CRUD
└── export.py                         (extended from main briefing)

backend/app/services/
├── export_engine.py                  (extended: versioning, watermarks, redaction maps)
├── completeness.py                   Completeness check logic
└── diff.py                           Version diff / change summary generation
```

---

## Build Phase Integration

These features slot into the existing build phases from the main briefing:

**Phase 3 (Review interface)** — add:
- The redaction log page (read-only view of decisions made so far, even during active review)

**Phase 5 (Export + audit)** — becomes the main phase for this briefing:
1. Draft preview (`<DraftPreview>`, side-by-side mode)
2. Document lifecycle: draft status, approval flow, completeness checks
3. Redaction log with filtering, grouping, batch operations
4. Draft comments
5. Export with concept/definitief modes, watermarking
6. Export versioning, re-export after changes
7. Redaction map generation
8. Redaction inventory (CSV/XLSX) generation
9. Change summary between export versions

**Phase 6 (Production hardening)** — add:
- Export job queue (Celery) for large dossier exports
- Export storage management (cleanup old concept-exports after final export)

---

## Implementation Notes

1. **The draft preview is a client-side overlay, not a server-rendered PDF.** Rendering a preview server-side for every change would be too slow. Instead, draw black rectangles on top of the pdf.js canvas at the coordinates of accepted detections. The article code text is rendered via a positioned HTML overlay (same technique as the text layer). This makes the preview instant and reactive to changes.

2. **The concept-export watermark** should be applied during server-side PDF generation (PyMuPDF): insert a diagonal "CONCEPT — Niet definitief" text on each page in light gray, large font, rotated 45°. This is a single PyMuPDF operation per page, cheap to apply.

3. **The redaction map** (companion PDF with colored overlays) is generated by rendering the original PDF and adding colored rectangle annotations (not redaction annotations — these are visual-only) at each detection's coordinates. Use different fill colors per Woo article. Add text labels with detection IDs. This document is for internal use only.

4. **Export versioning** is tracked via the `exports` table. When a re-export occurs, set `is_current = false` on all previous exports for that document/dossier, and create a new record with `is_current = true`. Old exports remain downloadable from the export history but are clearly marked as outdated.

5. **The change summary** (diff between versions) is computed by comparing the set of detection IDs and their statuses between two export snapshots. At export time, store a snapshot of all detection states as JSONB in the `exports` table. To generate the diff: compare snapshot N with snapshot N-1, list additions, removals, and modifications.

6. **The log table should use virtual scrolling** for large dossiers. A dossier with 200 documents could have 5000+ detections. Rendering all rows in the DOM would be slow. Use a virtual scroll library or implement windowed rendering — only render the rows visible in the viewport plus a buffer.

7. **Log filtering happens server-side** via query parameters on the API endpoint. The frontend sends filter state as query params (`?article=5.1.2e&status=deferred&reviewer=jan`), the backend returns the filtered, sorted, paginated result. Don't fetch all 5000 rows and filter client-side.

8. **Draft comments are lightweight by design.** They're not a full review/approval system — they're sticky notes. No threads, no assignments, no due dates. Just a text comment attached to a detection, with an open/resolved toggle. If the organization needs a formal review workflow, that's a future feature (and probably involves user authentication and roles, which are deferred to Phase 6).

9. **The approval completeness check is strict.** A document cannot be approved with any detection in "concept" status, any page unreviewed, or any draft comment unresolved. This is intentional — it prevents accidental publication of incomplete work. The check should list every blocking item as a clickable link, so the reviewer can jump directly to each one.

10. **Reopening an approved document is a significant action.** It invalidates the current export and resets the document to draft state. The confirmation dialog should make this very clear. The audit log entry for a reopen should include an optional reason field ("Naar aanleiding van bezwaarschrift" or "Nieuwe informatie ontvangen") for traceability.
