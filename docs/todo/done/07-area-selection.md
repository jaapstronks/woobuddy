# 07 — Area Selection Redaction

- **Priority:** P1
- **Size:** M (1–3 days)
- **Source:** Editing briefing, "Feature 2: Area Selection" section
- **Depends on:** ~~#05 (Mode toggle)~~ — done, #06 (Manual text redaction — reuses the floating bar + form; start after #06's polish pass)
- **Blocks:** Nothing

## Why

Not all sensitive content is selectable text. Signatures, stamps, photos, handwritten notes, and scanned page fragments inside an otherwise digital PDF all need redaction. Area selection is the escape hatch for "text selection can't reach it".

## Starting point (what #06 gives you for free)

Before writing anything, read these — area selection reuses most of them:

- `frontend/src/lib/components/review/PdfViewer.svelte` — the PDF stage already has `currentPage`, `scale`, `mode`, an `overlayEl`, and an `onManualSelection` callback pattern
- `frontend/src/lib/components/review/SelectionActionBar.svelte` — reusable as-is
- `frontend/src/lib/components/review/ManualRedactionForm.svelte` — reusable; needs a tiny tweak so the "Selectie" preview can render a placeholder when there is no text (area has no text)
- `frontend/src/lib/services/selection-bbox.ts` — defines `ManualSelection`, `SelectionAnchor`, the PDF-points coordinate model (origin top-left, 1 pt = 1/72 in), and the 0.5 pt slack used to prevent antialiasing bleed around black bars. **Match this exactly** so the two flows are interchangeable.
- `frontend/src/lib/stores/detections.svelte.ts::createManual` — already takes `bboxes` + `selectedText` + `entityType` + `tier` + `wooArticle` + `motivation`. Area just passes empty string for `selectedText` (or a placeholder) and `entityType: 'area'`.
- `frontend/src/routes/review/[docId]/+page.svelte` — already wires `manualSelection` / `manualStage: 'idle' | 'bar' | 'form'`. Area should feed into the **same** state machine so only one floating UI is ever visible.
- `backend/app/api/detections.py::create_manual_detection` + `ManualDetectionCreate` — `entity_type` is `str` server-side, so accepting `"area"` does not require a migration.

## Scope

### 1. Interaction in `PdfViewer.svelte`

- [ ] When `mode === 'edit'` and `Shift` is held, a **mousedown on the PDF stage** (not on an existing detection overlay, not on a text-layer span) starts an area draw. Mousedown without Shift keeps current behavior (text-layer selection).
- [ ] Draw a semi-transparent rectangle during drag, rendered in a dedicated `<div>` child of the PDF stage (e.g. `areaDrawEl`). Use a subtle fill (`rgba(27, 79, 114, 0.12)`) with a 1 px solid border matching `--color-primary`.
- [ ] On mouseup, if the rectangle has non-trivial size (≥ 6×6 px), emit a `ManualSelection` via `onManualSelection` with:
  - `page: currentPage`
  - `text: ''` (or an explicit placeholder like `'Handmatig geselecteerd gebied'`)
  - `bboxes: [<single bbox>]` in PDF points
  - `anchor: <SelectionAnchor>` computed from the rectangle's top/bottom edges (above if there's room, otherwise below), centered horizontally
- [ ] Tiny rectangles (< 6×6 px) are treated as an accidental click and silently dropped.
- [ ] Escape during drag cancels the in-progress rectangle.
- [ ] While drawing, suppress text-layer selection (set `user-select: none` on the text layer via a `drawing` class).

### 2. Coordinate conversion

- [ ] Capture mousedown/mousemove coordinates relative to the PDF stage using `getBoundingClientRect()` on the stage div (not on `textLayerEl` — area selection may intentionally land outside the text layer).
- [ ] Divide by `scale` to convert pixels → PDF points. Do **not** re-implement coordinate math inline; **extract a helper** into `selection-bbox.ts` (e.g. `rectToBoundingBox(rectPx, scalePixels, page, stageRect)`) and use it from both flows.
- [ ] Apply the same 0.5 pt `SLACK` as text selection so the black export bar covers the exact draw area.

### 3. Reusing the floating bar + form

- [ ] Feed the emitted `ManualSelection` into the existing `manualSelection` / `manualStage` state machine in `+page.svelte`. No new overlay component.
- [ ] `SelectionActionBar` is used as-is for the `bar` stage.
- [ ] `ManualRedactionForm` is used for the `form` stage. Adjust the "Selectie" preview block so an empty `selectedText` renders a placeholder chip ("Handmatig gebied — geen tekst") instead of an empty row.
- [ ] The form still pre-fills a motivation template from the chosen article — keep that behavior.

### 4. Type + store wiring

- [ ] Add `'area'` to the `EntityType` union in `frontend/src/lib/types/index.ts`.
- [ ] Add a Dutch label for `area` in `ManualRedactionForm.svelte`'s `ENTITY_LABELS` map ("Handmatig gebied").
- [ ] When an area selection opens the form, default `entityType` to `'area'` and skip the article → entity-type auto-nudge (an area has no implied type).
- [ ] `detectionStore.createManual` already handles this path — no changes needed.

### 5. Rendering the area detection

- [ ] `PdfViewer.drawOverlays` renders all detections via `getOverlayStyle`. Add an `entity_type === 'area'` branch that fills the rectangle with the same solid-black style as Tier 1 (area redactions are always accepted on creation). Small article code label in the corner is fine.
- [ ] `DetectionList.svelte` entries: detect `entity_type === 'area'` and render as "Handmatig gebied — pagina N" (no text preview).

### 6. Audit log

- [ ] Backend already logs `detection.manual_created` with `entity_type`, `tier`, `woo_article`, `bbox_count`. No content is logged. Nothing to change — just verify the log line fires when `entity_type: "area"` comes in.

## Not in Scope

- **OCR on the selected area** — future enhancement.
- **Auto-detecting image regions** — future; area selection is strictly manual.
- **Cross-page area selection** — an area is always a single rectangle on a single page.
- **Undo** — handled in #08.

## Acceptance Criteria

- In Edit Mode, `Shift + drag` draws a semi-transparent rectangle on the PDF page and opens the same floating bar as text selection on mouseup
- Rectangles smaller than 6×6 px are treated as misclicks and dropped
- Confirming "Lakken" opens `ManualRedactionForm`; confirming the form persists a detection with `source: "manual"`, `entity_type: "area"`, `review_status: "accepted"`, and the rectangle as a single bbox
- The detection renders as a filled black rectangle in the PDF overlay and appears in the sidebar as "Handmatig gebied — pagina N"
- Export (`/api/export/redact`) produces a gelakte PDF with the area fully covered
- Coordinates stay correct at any zoom level (tested at 50%, 100%, 200%)
- Escape cancels an in-progress draw; leaving Edit Mode clears any in-progress draw state
- No regressions in text selection flow from #06
