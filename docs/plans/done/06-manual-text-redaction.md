# 06 — Manual Text Selection Redaction

- **Priority:** P1
- **Status:** Done (polish pass 2026-04)
- **Source:** Editing briefing, "Feature 1: Manual Text Selection" section
- **Depends on:** #05 (Mode toggle) — done
- **Enriches:** #07 (Area selection), #08 (Undo/redo), #09 (Search-and-redact)

## What shipped

Manual text-selection redaction works end-to-end in Edit Mode:

1. Reviewer switches to Edit Mode (`M` key or toolbar).
2. Drag across the pdf.js text layer → native browser selection → `mouseup` captured in `PdfViewer.svelte`.
3. `selection-bbox.ts::snapRangeToWordBoundaries` snaps the range to word boundaries (unless `Alt` is held), `rangeToBoundingBoxes` resolves it to per-line PDF-space bboxes (with 0.5 pt slack for antialiasing), and `computeSelectionAnchor` produces a page-space anchor point.
4. The review page shows `SelectionActionBar` ("Lakken" / "Annuleren"); confirming swaps it for `ManualRedactionForm` (Woo article, entity type, motivation — recents pinned, motivation pre-filled from the article).
5. Form confirm → `detectionStore.createManual(...)` → POST `/api/detections` (`backend/app/api/detections.py::create_manual_detection`). The server stores bbox + metadata only, never the selected text.
6. New detection renders as an overlay and appears in the sidebar list.

## Polish pass (2026-04)

The initial implementation landed with Phase A; this pass addressed the rough edges flagged during review.

### Page-space anchor + scroll/zoom follow

The bar and form previously used `position: fixed` viewport coordinates captured at `mouseup`, so scrolling or zooming the PDF left them drifting off the selection.

- `SelectionAnchor` now stores `{ page, pdfX, pdfY, placement }` in **PDF points** relative to the text layer origin (same coordinate space as `BoundingBox`).
- `SelectionActionBar.svelte` and `ManualRedactionForm.svelte` take `stageEl` (the `.pdf-stage` element, exposed via `bind:stageEl` on `PdfViewer`) and `scale`, and reactively project the anchor to viewport pixels using `stageEl.getBoundingClientRect()`.
- They reproject on every scroll (capture-phase listener on `document`, so any ancestor scroller works), window resize, `ResizeObserver` on the stage, and any change to `scale` or the anchor itself.
- Zoom now also updates the position correctly — the previous viewport-coord snapshot would have become wrong as soon as the reviewer hit `+`/`−`.

### Edit-mode sidebar copy

`frontend/src/routes/review/[docId]/+page.svelte` previously told the reviewer "Handmatige bewerkingsopties (tekstselectie, gebiedsselectie, grens aanpassen) volgen in een latere stap." That was stale as soon as text selection landed. Replaced with short instructional copy ("Sleep over tekst om te lakken. Houd **Alt** voor letterprecisie.") plus the selected-detection summary below it. Shown whenever Edit Mode is active — no longer gated on having a detection selected.

### Cross-page selection invariant

The existing `textLayerEl.contains(range.commonAncestorContainer)` guard is sufficient only because we render one page at a time. Added a comment at the guard site noting that a future paginated/virtual-scroll rewrite needs a stronger check — `commonAncestorContainer` could sit in a shared parent and still span pages.

### Unit tests

`frontend/src/lib/services/selection-bbox.test.ts` covers:

- `snapRangeToWordBoundaries`: mid-word expansion, multi-word expansion, no-op on already-snapped selections, punctuation boundaries, non-text-node containers.
- `rangeToBoundingBoxes`: collapsed ranges, single-rect conversion with slack, horizontal merging on a visual line, preservation across lines, filtering of zero-sized rects.

Tests run under the existing `environment: 'node'` vitest config using small shims (a two-field `globalThis.Node` stub + plain-object fake Ranges) — no JSDOM dependency added. All 32 frontend tests green.

### Alt-for-character-precision

Verified by code review: `PdfViewer.handleTextLayerMouseUp` captures `e.altKey` at dispatch time before the `setTimeout(0)`, so the modifier state survives the deferral. `snapRangeToWordBoundaries` is skipped when `altKey` is true. A unit test pins the word-boundary behavior for regressions; manual browser verification is still recommended on next UI pass.

## Out of scope (handled elsewhere)

- **Undo of a manual creation** — #08. Backend still has no `DELETE /api/detections/:id`; #08 adds it.
- **Area selection** — #07, reuses `SelectionActionBar` and `ManualRedactionForm`.
- **Boundary adjustment of existing detections** — #11.

## Files touched

- `frontend/src/lib/services/selection-bbox.ts` — new `SelectionAnchor` shape; `computeSelectionAnchor` now takes `(range, container, scale, page)`.
- `frontend/src/lib/services/selection-bbox.test.ts` — new.
- `frontend/src/lib/components/review/PdfViewer.svelte` — `$bindable` `stageEl` prop, cross-page invariant comment, anchor call-site update.
- `frontend/src/lib/components/review/SelectionActionBar.svelte` — page-space projection, scroll/resize listeners, `ResizeObserver`.
- `frontend/src/lib/components/review/ManualRedactionForm.svelte` — same projection pattern as the bar.
- `frontend/src/routes/review/[docId]/+page.svelte` — `bind:stageEl`, threads `stageEl`/`scale` into bar/form, new edit-mode sidebar copy.
