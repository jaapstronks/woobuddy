# WOO Buddy — Supplementary Briefing: Manual Editing & Completeness Review

## Context

The main briefing describes a system that detects entities and passages, then presents them for human approval. This supplementary briefing addresses the other half of the workflow: the reviewer manually finding, selecting, adjusting, and redacting content that the system missed or got wrong.

In real Woo practice, automated detection will never be complete. Reviewers will always need to:

1. **Add** redactions the system missed entirely
2. **Adjust** the boundaries of detected entities (too narrow or too wide)
3. **Split** a detection that spans two different grounds
4. **Merge** adjacent detections that should be one redaction
5. **Verify completeness** — confirm they've actually reviewed every page

This is not an edge case workflow. For Tier 3 content (policy opinions, business data), the system only flags passages — the reviewer often needs to precisely select which sentences or phrases within a flagged passage should actually be redacted. And for any tier, false negatives are the dangerous failure mode: a missed BSN or a missed name is a privacy breach.

---

## Design Principle: Two Modes, One Viewer

The `<PdfViewer>` operates in two modes, toggled via a toolbar button or keyboard shortcut (`M`):

### Review Mode (default)

This is the mode described in the main briefing. The reviewer works through system-generated detections: clicking overlays, accepting/rejecting in the sidebar, moving to the next detection. The PDF is primarily a *reference* — the sidebar drives the workflow.

The cursor is a **pointer**. Clicking on the PDF selects a detection overlay (scrolling the sidebar to its card). Clicking on empty space deselects.

### Edit Mode

The reviewer interacts directly with the PDF to add or modify redactions. The PDF becomes the *primary interaction surface* — the sidebar shows context for whatever is selected.

The cursor is a **crosshair** (for area selection) or an **I-beam** (when hovering over selectable text). The reviewer can select text, draw rectangles, and manipulate existing redaction boundaries.

**The mode toggle must be highly visible.** Use a sticky toolbar button with clear labeling: "📋 Beoordelen" (Review) vs "✏️ Bewerken" (Edit). Show the active mode in the toolbar with a distinct background color so the reviewer always knows which mode they're in.

---

## Feature 1: Manual Text Selection → New Redaction

### Interaction flow

1. Reviewer enters Edit Mode
2. Reviewer **clicks and drags across text** in the PDF to select it — just like selecting text in a browser. The selected text highlights in the application's selection color.
3. On mouse-up (text selected), a **floating action bar** appears near the selection — positioned just above or below the selected text, never obscuring it. The bar contains:
   - A **"Lakken" (Redact)** button — primary action
   - A **"Annuleren" (Cancel)** button — dismisses the selection
4. Clicking "Lakken" opens a **compact inline form** (replaces the floating bar, same position):
   - **Woo article selector** — dropdown with all applicable articles, grouped by tier. Most-used articles at the top. The five most recently used articles in this dossier should be pinned. Format: `5.1.2e — Persoonlijke levenssfeer`
   - **Entity type selector** (optional) — for Tier 1/2 style detections: persoon, adres, telefoonnummer, etc. Pre-filled when the article selection implies a type (selecting 5.1.1e auto-suggests "identificatienummer").
   - **Motivation text** — pre-filled with a template based on the selected article, editable. For frequently used articles, the template should be good enough that the reviewer rarely needs to edit it.
   - **"Bevestigen" (Confirm)** button
5. On confirm, the selection becomes a new detection in the database:
   - Stored with `source: "manual"`, tier based on the selected article, `review_status: "accepted"` (it's immediately confirmed since the human created it)
   - The PDF overlay updates: the selected text gets a black redaction bar with the article code
   - The detection appears in the sidebar list
   - Audit log entry records who added what, when

### Text selection implementation

PDF.js renders text in a **text layer** — invisible `<span>` elements positioned over the canvas, matching the PDF's text coordinates. This is what makes native text selection work. The key behaviors:

- Selection must **snap to word boundaries** by default (whole-word selection). The reviewer can override to character-level precision by holding `Alt` while selecting.
- Selection can **span multiple lines** within a page — this is natural browser text selection behavior and should just work with the text layer.
- Selection **cannot span pages** — if the reviewer needs to redact across a page break, they create two separate redactions.
- **Multi-span selections** are supported: the reviewer selects text, and the system resolves it to one or more bounding boxes based on the underlying text layer spans. A single manual selection may map to multiple `bbox` entries if the text wraps across lines.

### The floating action bar

This UI element is critical to get right. Reference pattern: Google Docs' floating toolbar that appears on text selection, or Medium's inline formatting bar.

- **Position**: Horizontally centered above the selection. If the selection is near the top of the viewport, position it below instead. Never obscure the selected text.
- **Appearance**: Small, rounded, semi-translucent background (frosted glass effect or solid with subtle shadow). Two buttons: primary "Lakken" and ghost "Annuleren".
- **Dismissal**: Clicking anywhere outside the selection or pressing `Escape` dismisses both the selection and the bar.
- **Keyboard**: `Enter` triggers "Lakken" (opens the article form), `Escape` cancels.

---

## Feature 2: Area Selection → New Redaction (for non-text content)

Not all content is text. Tables, images, headers with embedded fonts, or scanned content within an otherwise digital PDF may not have selectable text. For these cases:

### Interaction flow

1. In Edit Mode, the reviewer holds `Shift` and **drags a rectangle** on the PDF page
2. A semi-transparent rectangle appears while dragging, snapping to the drag coordinates
3. On mouse-up, the same floating action bar appears with "Lakken" and "Annuleren"
4. The rest of the flow is identical to text selection — article selector, motivation text, confirm

### Area selection specifics

- The rectangle is stored as a `bbox` (x0, y0, x1, y1) without associated text
- Since there's no extracted text, the detection record stores `entity_text: null` and `entity_type: "area"`
- In the sidebar, these show as "Handmatig geselecteerd gebied" with a thumbnail of the area
- Area redactions are particularly important for:
  - Signatures and handwritten annotations
  - Photos or images of people
  - Tables where individual cells contain sensitive data
  - Letterheads with personal contact details

---

## Feature 3: Boundary Adjustment on Existing Detections

When the system detects an entity but the boundaries are wrong — too narrow (missing part of a name) or too wide (including surrounding text that shouldn't be redacted) — the reviewer needs to adjust.

### Interaction flow

1. In Edit Mode, the reviewer **clicks on an existing detection overlay** in the PDF
2. The overlay enters **edit state**: the highlight color changes to a distinct editing color (blue border with corner/edge handles), and the overlay becomes interactive
3. The reviewer can:

**a) Resize via handles:**
For simple rectangular detections (single bbox), display resize handles on the four edges and four corners. Dragging an edge or corner expands or shrinks the redaction area. This works well for area-type detections and single-line text detections.

**b) Extend/shrink text selection:**
For text-based detections (those with associated text layer spans), the adjustment should work like extending a text selection:
- **Shift+click** on a word adjacent to the detection to extend the boundary to include it
- **Alt+click** on a word at the edge of the detection to shrink the boundary, excluding that word
- The detection's `entity_text`, `start_char`, `end_char`, and `bbox` values update accordingly

**c) Keyboard-driven adjustment:**
- When a detection is in edit state, `←` and `→` shrink/extend by one word (or one character with `Alt` held)
- This is the fastest method for precise adjustments and should be documented in the keyboard shortcuts overlay

4. While in edit state, the sidebar shows the detection card with a live preview of the adjusted text, highlighted to show what changed
5. The reviewer clicks **"Opslaan" (Save)** in the sidebar card or presses `Enter` to confirm the adjustment
6. Pressing `Escape` reverts to the original boundaries

### What gets stored

- The detection record updates with new `start_char`, `end_char`, `bbox` values
- `review_status` changes to `"edited"`
- An audit log entry records the original and new boundaries, the editor, and the timestamp
- If the detection was propagated from another occurrence, the adjustment applies **only to this instance** — other propagated instances keep their original boundaries (with an option to "propagate this adjustment too")

---

## Feature 4: Split and Merge

### Splitting a detection

Sometimes the system detects a passage that contains two different types of sensitive information under two different grounds. For example, a sentence containing both a personal name (5.1.2e) and a medical term (5.1.1d).

1. In Edit Mode, the reviewer clicks on a detection to enter edit state
2. The reviewer clicks **"Splitsen" (Split)** in the sidebar card
3. The reviewer **clicks a position within the detected text** to define the split point — the text layer highlights to show the two resulting segments
4. Two new detection cards appear in the sidebar, each editable independently (different article, different motivation)
5. The original detection is replaced by the two new ones in the database

Splitting should feel lightweight. No modal, no extra confirmation. Click "Splitsen", click the split point, done — now there are two cards to fill in.

### Merging detections

Adjacent or overlapping detections that should be a single redaction can be merged:

1. In Edit Mode, the reviewer selects multiple detections by `Ctrl+clicking` them in the PDF or sidebar
2. A **"Samenvoegen" (Merge)** button appears in the toolbar
3. Clicking it creates a single detection spanning the combined area, keeping the article and motivation from the first detection (editable)
4. The individual detections are removed and replaced by the merged one

---

## Feature 5: Page-Level Completeness Review

After working through all system detections, the reviewer needs to verify they haven't missed anything. The tool should support a **page-by-page sweep** workflow.

### Page status indicators

Each page in the document gets a status, displayed in a **page strip** (horizontal row of page thumbnails at the top or bottom of the PDF viewer) and in the sidebar's page navigation:

| Status | Icon | Meaning |
|--------|------|---------|
| Unreviewed | ○ (empty circle) | No manual review yet — only system detections |
| In progress | ◐ (half circle) | Some detections reviewed, but page not marked complete |
| Complete | ● (filled circle, green) | Reviewer has confirmed this page is fully reviewed |
| Flagged | ⚑ (flag, amber) | Reviewer wants to return to this page later |

### Marking pages complete

At the bottom of each page in the PDF viewer (or as a floating button in the corner), display a **"Pagina beoordeeld ✓" (Page reviewed)** button. Clicking it:

- Sets the page status to "complete"
- The page thumbnail in the strip gets a green checkmark
- An audit log entry records who reviewed which page, when

The reviewer can also flag a page for later: **"Later terugkomen ⚑"** sets the status to "flagged."

### Document completion

The document cannot be moved to "approved" status until:
- All pages are marked "complete" (no unreviewed or in-progress pages)
- All Tier 2 detections are accepted or rejected (none left pending)
- All Tier 3 annotations are resolved (redacted, not-redacted, or deferred)

The progress toolbar should make this explicit: "12/15 pagina's beoordeeld · 3 detecties openstaand"

If the reviewer tries to approve with incomplete items, show a clear warning listing exactly what's still open — not a vague "there are items remaining."

---

## Feature 6: Search-and-Redact

A common workflow in Woo practice: the reviewer knows a specific name, term, or number appears throughout the document and wants to redact all occurrences at once. This bridges automated detection and manual editing.

### Interaction flow

1. Toolbar contains a **search field** (or `Ctrl+F` opens it) with a toggle: "Zoek & Lak" mode
2. The reviewer types a search term (e.g., "Van der Berg" or a phone number)
3. All occurrences are highlighted in the PDF with a distinct search-result color (different from detection highlights)
4. The sidebar shows a list of all occurrences with their page numbers and surrounding context
5. The reviewer can:
   - **"Alles lakken" (Redact all)** — opens the article selector once, applies to all occurrences
   - **Cherry-pick** — check/uncheck individual occurrences before applying
   - **Refine** — toggle between exact match and fuzzy match (to catch "v.d. Berg", "Van den Berg", "vd Berg" etc.)

### Why this matters

Woo documents often contain hundreds of pages. A person's name might appear 50+ times. The reviewer who spots a missed name on page 37 shouldn't have to manually scroll through 200 pages to find the other 49 occurrences. Search-and-redact makes this a 10-second operation.

This also naturally supports the **name propagation** feature from the main briefing: when a reviewer uses search-and-redact, the result is functionally identical to propagation — every occurrence gets the same article and motivation.

---

## Feature 7: Undo/Redo

All editing operations in Edit Mode must be undoable. This is fundamental for a tool where a misclick can redact the wrong passage.

### Implementation

- Maintain an **undo stack** per document per session (in-memory, not persisted)
- `Ctrl+Z` undoes the last action, `Ctrl+Shift+Z` or `Ctrl+Y` redoes
- Undoable actions: add manual redaction, adjust boundaries, split, merge, accept/reject detection, mark page complete, search-and-redact
- Undo should feel instant — no confirmation dialog
- The undo stack clears when the document is closed or the session ends
- The **audit log is not affected by undo** — it records the original action AND the undo, providing a full trail

### Visual feedback

When an undo occurs, briefly flash the affected area in the PDF (e.g., a 300ms highlight pulse) so the reviewer can see what changed.

---

## Revised Toolbar Layout

The PDF viewer toolbar needs to accommodate both Review Mode and Edit Mode. Proposed layout:

```
┌──────────────────────────────────────────────────────────────────────┐
│  [📋 Beoordelen] [✏️ Bewerken]  │  [🔍 Zoek & Lak]  │  ◀ 3/12 ▶  │
│                                  │                    │             │
│  --- When in Edit Mode: ---      │  [↩ Ongedaan]      │  [⊕ 🔲]    │
│  Active tool indicators          │  [↪ Opnieuw]       │  zoom       │
└──────────────────────────────────────────────────────────────────────┘
```

Left section: Mode toggle (always visible), plus tool indicators when in Edit Mode
Center section: Search-and-redact field, undo/redo buttons
Right section: Page navigation, zoom controls

When in Edit Mode, the toolbar should subtly change its background or border color to reinforce which mode is active — for instance, a thin blue top-border vs. the default neutral.

---

## Sidebar Behavior in Edit Mode

When Edit Mode is active, the sidebar adapts:

- If **nothing is selected** in the PDF: the sidebar shows the full detection list (same as Review Mode), but with an "Add manual redaction" prompt at the top
- If **existing detection is clicked**: the sidebar shows that detection's card in edit state — with boundary adjustment controls, split/merge buttons, and the article/motivation fields
- If **new text/area is selected**: the sidebar shows the new-redaction form (article selector, entity type, motivation template)
- If **search-and-redact is active**: the sidebar shows the list of search results with check/uncheck and the batch-apply controls

The key insight: **the sidebar is always contextual to what's happening in the PDF viewer**. It never shows a separate, disconnected editing interface.

---

## Database Changes

The `detections` table needs these additional fields to support manual editing:

- `source` field should support values: `"deduce"`, `"regex"`, `"llm"`, `"manual"`, `"search_redact"`
- `original_bbox` — stores the original bounding box before any boundary adjustments, for audit purposes
- `split_from` — UUID reference to the detection this was split from (null for originals)
- `merged_from` — JSON array of UUIDs for detections that were merged into this one (null for originals)

New table:

- **`page_reviews`** — tracks per-page review status (document_id, page_number, status, reviewer, timestamp)

---

## Keyboard Shortcuts (Complete)

Consolidating shortcuts from the main briefing with the editing additions:

### Global (both modes)

| Key | Action |
|-----|--------|
| `M` | Toggle between Review and Edit mode |
| `Ctrl+F` | Open search-and-redact |
| `Ctrl+Z` | Undo |
| `Ctrl+Shift+Z` | Redo |
| `?` | Show shortcut help overlay |
| `←` / `→` | Previous/next page (when no detection selected) |

### Review Mode

| Key | Action |
|-----|--------|
| `A` | Accept current detection |
| `R` | Reject current detection |
| `D` | Defer current detection |
| `↑` / `↓` | Previous/next detection in sidebar |
| `1`-`9` | Quick-select article (mapped to most-used articles in this dossier) |

### Edit Mode

| Key | Action |
|-----|--------|
| `Enter` | Confirm current action (redact selection, save boundary edit) |
| `Escape` | Cancel current action / deselect |
| `←` / `→` | Shrink/extend selection by one word (when detection in edit state) |
| `Alt+←` / `Alt+→` | Shrink/extend by one character |
| `P` | Mark current page as reviewed |
| `F` | Flag current page for later review |

---

## Implementation Notes

1. **Text selection relies on pdf.js's text layer.** The text layer consists of absolutely-positioned `<span>` elements. Use the browser's native `Selection` API (`window.getSelection()`) to determine which spans the user selected, then map those spans back to the extracted text positions from PyMuPDF. This mapping is the tricky part — the text layer span boundaries don't always align perfectly with the extraction spans. Build a reconciliation layer that fuzzy-matches selected DOM text back to the stored text spans.

2. **The floating action bar should be a Svelte component** (`<SelectionActionBar>`) that positions itself relative to the selection rectangle using `getBoundingClientRect()` on the selection's range. It should use `position: fixed` and recalculate on scroll.

3. **Area selection (Shift+drag)** is implemented as a custom canvas overlay on top of the PDF page. Draw a semi-transparent rectangle while dragging. On mouse-up, convert the canvas coordinates to PDF coordinates using the current viewport transform (zoom level, scroll offset). Store as a bbox.

4. **Boundary adjustment handles** should be rendered as small colored squares (8×8px) at the edges and corners of the selected detection's overlay. Use CSS `cursor: ew-resize`, `ns-resize`, etc. for the appropriate handles. On drag, recalculate the bbox and update the overlay in real time.

5. **For text-based boundary adjustment** (Shift+click to extend, Alt+click to shrink), the system needs to track which text layer `<span>` elements are included in the detection. When the reviewer Shift+clicks a word, find the nearest `<span>`, include it in the detection's span set, and recalculate the bounding boxes.

6. **Page review status should persist immediately** — don't wait for a save action. Write to the `page_reviews` table on each status change. This prevents data loss if the browser crashes mid-review.

7. **Search-and-redact fuzzy matching** can use a simple approach for the prototype: normalize both the search term and the document text (lowercase, remove diacritics, collapse whitespace), then match. For name variants ("van der" vs "v.d." vs "vd"), maintain a small set of Dutch name-particle normalization rules. A full fuzzy matching library is overkill for phase 1.

8. **The undo stack should store commands, not snapshots.** Each undoable action is a reversible command object: `{ type: "add_detection", detection_id, forward: () => ..., reverse: () => ... }`. This keeps memory usage low and makes redo trivial.

9. **Don't block Edit Mode behind completing Review Mode.** The reviewer should be able to freely switch between modes at any time. A common workflow: start in Review Mode, process system detections, notice something the system missed, switch to Edit Mode to add it, switch back to Review Mode to continue. The mode toggle should be instant with zero friction.

10. **The mode distinction is primarily about cursor behavior and what click events do.** Both modes show the same PDF with the same overlays. The difference is whether clicking selects a detection card (Review) or initiates a boundary edit (Edit). Keep the visual difference minimal — just the toolbar indicator and cursor shape.
