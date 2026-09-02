# 69 — Review screen: O(N²) hot paths, bulk IDB writes, keyboard/a11y gaps

> Status: aanzet · 2026-09-02 · TODO #69 · hangt samen met: —

- **Priority:** P2 (felt on 200+ detection documents; a11y is a stated promise)
- **Size:** M
- **Source:** tighten-scan 2026-09-02

> Agent measurements on `origin/main` @ `83fecbb`; re-verify before editing.
> Second pass (review of PR #99, 2026-09-02): all ten findings hold; one
> pointer corrected (finding 2) and two claims narrowed (1, 4).

## Perf

1. `components/review/DetectionList.svelte:286` calls `sameNameCount(det)` per
   row inside the render loop; `findSameNameDetections` scans `allDetections`.
   O(P·N) on every mutation, with P the number of `persoon` rows (non-persoon
   rows return 0 early). Hoist to one `$derived` map.
2. `stores/detections.svelte.ts:548-560` `acceptAllPendingTier1` /
   `acceptHighConfidenceTier2` await `accept()` per row; each `review()`
   reassigns `allDetections` (5 derived passes) and does a full IDB
   read-modify-write. 200 rows = 200 transactions. Same shape in
   `routes/review/[docId]/log/+page.svelte:311-336` (`confirmBulk`, per-row
   `review()`/`remove()` at 317-328). Add a batch mutate + single persist.
3. `services/pdf-overlay-draw.ts:67` clears `innerHTML` and rebuilds every
   rectangle + listener on every detection change, including off-page flips.
4. `log/+page.svelte` recomputes filter → sort → stats (`:116,140,184`) on every
   keystroke in the page-number filter (`:539-544`, the only text input).
5. `PdfViewer.svelte:203-214` never calls `pdfDoc.destroy()` on the previous
   document; re-attaching a PDF leaks a worker per swap.

## A11y and keyboard

6. `DetectionList.svelte:243-303`: native `<button>` cards containing
   `<sl-button>` children. Nested interactive content: invalid HTML, broken
   tab order.
7. `pdf-overlay-draw.ts:87-126`: overlays are `div`s with a click listener, no
   `role`/`tabindex`/`aria-label`. The PDF overlay has no keyboard path;
   `PdfViewer.svelte:510-511,526` suppress the lints.
8. `ManualRedactionForm.svelte:126` `role="dialog"` without `aria-modal`,
   focus trap or initial focus.
9. `services/review-pdf-loader.ts:92-102` `pickPdfFile` never resolves when
   the picker is dismissed (no `cancel` listener); the doc comment says it
   resolves `null`.
10. `services/export-service.ts:104-110` revokes the object URL synchronously
    after `click()`; unreliable for large blobs in Firefox/Safari.

## Gate

- A vitest that runs `acceptAllPendingTier1` on 500 detections and asserts a
  single `session-state-store` write.
- Re-enable the two suppressed a11y lints once overlays are focusable.

## Acceptance criteria

- [ ] Bulk accept of 200 Tier-1 rows performs one IDB write.
- [ ] Every overlay rectangle is reachable and activatable by keyboard.
- [ ] Cancelling the re-attach file picker returns to the normal state.
