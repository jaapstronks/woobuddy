# 09 — Search-and-Redact

- **Priority:** P1
- **Status:** Done
- **Source:** Editing briefing, "Feature 6: Search-and-Redact" section
- **Depended on:** #06 (Manual text redaction) — done

## What shipped

Fully client-side search-and-redact, reusing the text already extracted for
the detection pipeline. No server call for search itself; only the final
bulk-create talks to `/api/detections`.

### Search service

`frontend/src/lib/services/search-redact.ts` implements `searchDocument(query,
extraction, existingDetections) → SearchOccurrence[]`. Per page it:

1. Concatenates trimmed `textItems` with single-space separators, tracking
   each item's `[start, end)` offset in the joined string.
2. Lowercases query + page string, collapses whitespace runs in the query,
   and rejects queries shorter than 2 characters post-normalization.
3. `indexOf`-scans for matches; for each match, collects the overlapping
   items and merges their bboxes into one box per visual line (same rule as
   the manual text selection flow in #06).
4. Flags matches whose bboxes are ≥50% covered by an existing detection as
   `alreadyRedacted` — those render in a muted "al gelakt" list so the
   reviewer doesn't double-redact.
5. Steps past each match end so `"aa"` in `"aaaa"` yields two occurrences,
   not three overlapping ones.

Unit tests in `search-redact.test.ts` cover exact match, case-insensitive,
whitespace normalization, multi-page, zero matches, context snippets,
overlap flagging (positive + negative), and the non-overlap step rule.

### Search store

`frontend/src/lib/stores/search.svelte.ts` owns UI state: `open`, `query`,
`selectedIds`, and a `focusedId` for the single-highlight emphasis. Results
are a `$derived` over `detectionStore.extraction + detectionStore.all` so
typing re-runs search reactively and any redaction that lands during a
search session automatically re-flags overlapping hits. An
`effectiveSelected` derived list intersects `selectedIds` with the live
`redactable` set so stale ids (from a narrowed query) can't leak into
bulk redaction. Module-scope `$effect` isn't allowed in a `.svelte.ts`
store, so the pruning is expressed as the derived intersection instead.

### Search panel

`frontend/src/lib/components/review/SearchPanel.svelte` renders inside the
existing sidebar when the store is open:

- `sl-input` with clearable text, autofocus via `queueMicrotask` (Shoelace
  shadow DOM needs a tick before `.focus()` lands).
- Result count, "al gelakt" count, toggleable "alles selecteren".
- Occurrence rows with a checkbox, page badge, and a highlighted context
  snippet (~24 chars each side) with the match wrapped in `<mark>`.
- Clicking a row focuses the hit and jumps the PDF to that page.
- `<sl-dialog>` article picker (Woo-grond · type · motivering) opened by
  "Lak alles" / "Lak geselecteerde". Reuses the same article list,
  recent-articles LRU, and ARTICLE_TO_ENTITY nudge as
  `ManualRedactionForm`. Kept as its own component rather than reusing
  `ManualRedactionForm` directly because that form requires viewport-anchor
  projection — anchored to a PDF selection — which doesn't apply to a
  bulk action.
- `Escape` closes the picker if open, otherwise closes the panel.

### PDF viewer highlights

`PdfViewer.svelte` now takes `searchHighlights` and `focusedSearchId`
props. A dedicated `searchLayerEl` DOM layer sits above the canvas and
below the detection overlay, rendered by `drawSearchHighlights()` on a
separate `$effect` so typing in the search box doesn't force a detection
re-render. Styles:

- Regular hit — translucent yellow with a dark-yellow border.
- Focused hit (clicked in the list) — brighter yellow + glowing shadow.
- Already-redacted hit — muted grey dashed border.

The layer is `pointer-events: none` — reviewers act on search hits through
the sidebar, not by clicking through the PDF, so the new layer doesn't
fight the detection overlay or the text layer for clicks.

### Bulk-create via undo

The review page wraps the picker confirmation in a `BatchCommand` of
`CreateManualCommand` children (one per occurrence) with `source:
'search_redact'`. Single `Ctrl+Z` undoes the whole sweep. `CreateManualCommand`
gained an optional `source` field plumbed through
`detectionStore.createManual` → `CreateManualDetectionRequest` → backend.

### Backend: source differentiation

`ManualDetectionCreate` schema gained `source: Literal["manual",
"search_redact"] = "manual"`. The `POST /api/detections` handler passes it
through to the DB row so audit logs can distinguish the two paths. The
`DELETE /api/detections/:id` eligibility check now accepts either value so
the undo stack can still reverse bulk search-redact rows. The audit log
entry for `detection.manual_created` includes `source`.

### Ctrl+F + toolbar button

`Ctrl/Cmd+F` opens the search panel (preventDefault — browser find can't
see pdf.js's text layer anyway), and opens the sidebar if closed. A search
icon next to the export button in the top toolbar toggles the same state.

## Out of scope (deferred)

- Fuzzy Dutch name-particle matching (`v.d.`, `vd`, `van den`) — P3.
- Cross-document search within a dossier — the app is single-document.
- Search within a single page only (currently always whole-document).

## Files touched

**New:**

- `frontend/src/lib/services/search-redact.ts`
- `frontend/src/lib/services/search-redact.test.ts`
- `frontend/src/lib/stores/search.svelte.ts`
- `frontend/src/lib/components/review/SearchPanel.svelte`

**Modified:**

- `frontend/src/lib/components/review/PdfViewer.svelte` — `searchHighlights`
  + `focusedSearchId` props, `searchLayerEl`, `drawSearchHighlights`,
  `SearchHighlight` interface export, CSS for the new layer.
- `frontend/src/routes/review/[docId]/+page.svelte` — Ctrl+F handler,
  toolbar search button, `SearchPanel` mounted in the sidebar,
  `handleRedactOccurrences` batch-command builder, derived
  `searchHighlights`.
- `frontend/src/lib/stores/detections.svelte.ts` — exposes `extraction`
  getter; `createManual` accepts optional `source`.
- `frontend/src/lib/stores/undo.svelte.ts` — `CreateManualCommand` accepts
  optional `source`, label varies accordingly.
- `frontend/src/lib/api/client.ts` — `CreateManualDetectionRequest.source`.
- `backend/app/api/schemas.py` — `ManualDetectionCreate.source` literal.
- `backend/app/api/detections.py` — plumbs source through, DELETE allows
  `search_redact`, audit log includes source.
