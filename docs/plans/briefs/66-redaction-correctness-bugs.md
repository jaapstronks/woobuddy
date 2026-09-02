# 66 — Redaction-correctness bugs (scan 2026-09-02)

> Status: aanzet · 2026-09-02 · TODO #66 · hangt samen met: —

- **Priority:** P0 (wrong or missing black boxes, silent data loss)
- **Size:** M
- **Source:** tighten-scan 2026-09-02 (four Opus read-only agents + manual verification by Fable)

> Scan output. Line numbers were verified against `origin/main` @ `83fecbb` on
> 2026-09-02 but are agent measurements: re-verify before editing. Items marked
> **confirmed** were checked by hand; **plausible** were read-derived only.
> Second pass (review of PR #99, 2026-09-02): all ten findings re-verified
> against the code; every line reference held to within ±1.

## Why

Every item below changes what ends up (or fails to end up) under a black box, or
silently discards reviewer work. They are ordered by blast radius.

## Findings

1. **Custom-term redactions all get page-1 boxes — confirmed.**
   `backend/app/services/pipeline_custom_terms.py:93-96` caches
   `find_span_for_text(extraction.pages, m.term)` per lowercased term without
   `occurrence_index`; `span_resolver.py:473-474` stops at the first page with
   a hit. Every later occurrence of a reviewer-typed term (page 2..N) gets the
   page-1 bbox set, so those occurrences export **unredacted**. The
   occurrence-aware helper `_resolve_bboxes` (`pipeline_engine.py:320-339`) is
   used for every NER hit but not here. Fix: route custom terms through
   `_resolve_bboxes` with the match's char offset; add a multi-page fixture test.
2. **Split and merge are not undoable — confirmed.**
   `frontend/src/lib/stores/split-merge.svelte.ts:52,56` call
   `detectionStore.split/merge` directly; no `SplitCommand`/`MergeCommand`
   exists in `stores/undo/`. Ctrl+Z after a merge reverts an unrelated action.
3. **Motivation text is silently discarded — confirmed.**
   `services/review-actions.ts:124` sends `motivation_text`, but
   `stores/detections.svelte.ts` `review()` (~line 270-317) only handles
   `review_status`, `woo_article`, `bounding_boxes`, `subject_role`. The
   "Opslaan" button in `MotivationEditor.svelte:37` only flips status. Either
   persist it (and surface it in the log/onderbouwing) or remove the field.
4. **Arrow keys nudge the bbox *and* jump detections — confirmed by listener order.**
   `KeyboardShortcuts` mounts at `routes/review/[docId]/+page.svelte:631`
   (window listener, handles `arrowleft/right`), `PdfViewer` at `:952` and
   only after the document resolves. `boundary-edit-controller.svelte.ts:216-225`
   relies on `stopImmediatePropagation` but its listener registers second, so it
   runs second. Fix: a shared "edit mode active" guard checked by `KeyboardShortcuts`.
5. **Out-of-range redactions are dropped without a trace.**
   `backend/app/services/pdf_engine.py:314-317` and
   `pdf_accessibility.py:128-129` `continue` on a bad page index: no counter,
   no log, export "succeeds". Return a count of skipped boxes and surface it.
6. **Occurrence index counted in two different domains — plausible.**
   `pipeline_engine.py:330-333` counts hits in `full_text`;
   `span_resolver.py:372-381` counts at most one hit per text span. A span that
   contains the same name twice desynchronises them and the bbox lands on the
   wrong occurrence. Needs a fixture with a repeated name inside one span.
7. **In-flight render swallows the next page change — plausible.**
   `PdfViewer.svelte:216-218` returns on `if (rendering)` and never re-queues,
   while overlays (`:342-377`) draw for the new page on the old canvas. Add a
   trailing-edge pending-render slot.
8. **Split point uses live `scale`, overlays use `renderedScale` — plausible.**
   `PdfViewer.svelte:254-258` vs `:358-372`. During a fit recompute the split
   lands at the wrong x.
9. **Export decides "accepted" with a hand-rolled predicate.**
   `services/export-service.ts:44` re-implements `isAcceptedRedaction`
   (`utils/review-status.ts:90`, 7 other call sites). This is the one place
   where drift changes what gets burned in.
10. **Undo `push` silently drops commands while busy.**
    `services/review-actions.ts:56-88` call `undoStore.push` unawaited;
    `undo.svelte.ts:62` returns when `busy`. Rapid A/R/D keypresses vanish.

## What the session does

- Fix 1, 2, 3, 4, 5, 9 first (all confirmed). Then reproduce 6, 7, 8, 10 with
  a failing test before touching code.
- Add the missing tests that would have caught these: `export-service` merge of
  accepted + auto-accepted detections; `detections.svelte.ts` split/merge/undo
  round-trip; backend custom-term multi-page fixture.

## Gate (what stops regrowth)

- A vitest for `export-service` that asserts the redaction list equals
  `allDetections.filter(isAcceptedRedaction)`.
- A backend regression fixture where the same custom term occurs on pages 1 and 3.
- Undo tests that cover split/merge, not just the stack.

## Jaap decides

- Item 3: keep and persist motivation text, or drop the field from the UI?

## Acceptance criteria

- [ ] Custom term on page 3 exports redacted; test proves it.
- [ ] Ctrl+Z reverts a split and a merge.
- [ ] Arrow keys during boundary edit do not change the selected detection.
- [ ] Export logs and reports the number of skipped out-of-range boxes.
