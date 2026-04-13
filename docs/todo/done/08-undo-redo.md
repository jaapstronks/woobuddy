# 08 — Undo / Redo

- **Priority:** P1
- **Size:** M (1–3 days)
- **Source:** Editing briefing, "Feature 7: Undo/Redo" section
- **Depends on:** ~~#05 (Mode toggle)~~ — done, #06 (Manual text redaction — finish polish pass first), and ideally #07 (Area selection) so the command set is complete
- **Blocks:** Nothing, but every editing feature benefits from it

## Why

A misclick in Edit Mode can redact the wrong passage. Without undo, reviewers will be afraid to experiment, and the entire editing loop feels fragile. Undo is table-stakes for any editing surface.

## Current state (2026-04)

Nothing exists yet. Relevant context for whoever picks this up:

- `frontend/src/lib/stores/detections.svelte.ts` is the single source of truth for in-memory detections and exposes `createManual`, `accept`, `reject`, `defer`, `review`. Any undo store should interact with these methods (or their underlying server calls), not bypass them.
- `frontend/src/lib/components/review/KeyboardShortcuts.svelte` is the global shortcut hub — already handles `A`, `R`, `D`, `M`, arrow keys, `?`. Add `Ctrl+Z` / `Ctrl+Shift+Z` / `Ctrl+Y` here, with the usual "ignore when focus is in INPUT/TEXTAREA/SELECT" guard already present (and extend the guard to Shoelace form elements — `sl-input`, `sl-textarea`, `sl-select` — since users type in the manual redaction form).
- **The backend has no `DELETE /api/detections/:id` endpoint today.** See `backend/app/api/detections.py` — only `GET` (list), `POST` (manual create), `PATCH` (review). Undoing a manual create cleanly requires adding `DELETE /api/detections/:id`. See "Backend" section below.
- Manual and area detections carry `source: "manual"` + `review_status: "accepted"` from birth. NER detections carry `source: "auto"` (Deduce/Tier 2) or `"regex"` (Tier 1) and start in `pending` or `auto_accepted`. The undo semantics differ by origin — undo of an auto detection flips its status back; undo of a manual detection deletes the row.

## Design

### Command-based undo stack

- [ ] New file: `frontend/src/lib/stores/undo.svelte.ts`
- [ ] State: `undoStack: Command[]`, `redoStack: Command[]` held in `$state` arrays
- [ ] `Command` interface: `{ label: string; forward(): Promise<void>; reverse(): Promise<void>; affectedDetectionIds: string[]; }`
- [ ] Actions: `push(cmd)`, `undo()`, `redo()`, `clear()`
- [ ] `push` executes `forward()` and appends to `undoStack`, clearing `redoStack`
- [ ] `undo` pops from `undoStack`, calls `reverse()`, pushes onto `redoStack`
- [ ] `redo` pops from `redoStack`, calls `forward()`, pushes onto `undoStack`
- [ ] Stack is **per-session, in-memory only** — no IndexedDB, no cross-reload persistence. Clearing the document or navigating away clears the stack (hook into `$effect` cleanup in `/review/[docId]/+page.svelte`).
- [ ] A soft cap of ~100 entries to keep memory bounded; drop the oldest when exceeded.

### Command types to ship in the first pass

- [ ] **CreateManualCommand** — `forward`: call `detectionStore.createManual(...)` and store the returned id; `reverse`: `DELETE /api/detections/:id` and splice it out of `detectionStore.all`.
- [ ] **ReviewStatusCommand** — `forward`: `detectionStore.review(id, { review_status: next })`; `reverse`: `detectionStore.review(id, { review_status: previous })`. Used for accept/reject/defer. Capture `previous` at command-construction time.
- [ ] **BatchCommand** — wraps an array of commands so the whole "Accept all Tier 1" batch action undoes as a single `Ctrl+Z`. Runs children in order on forward, reverse order on reverse.

Future command types (not in scope now, but leave room): boundary adjustment (#11), split/merge (#12), page-complete toggle (#10), search-and-redact batch (#09).

### Wiring existing actions through the undo store

- [ ] In `/review/[docId]/+page.svelte`, replace direct calls to `detectionStore.createManual`, `accept`, `reject`, `defer`, and batch actions with `undoStore.push(new XxxCommand(...))`. Keep the store methods themselves unchanged — commands call into them.
- [ ] `handleFormConfirm` in `+page.svelte` wraps `detectionStore.createManual` in a `CreateManualCommand`.
- [ ] `handleAccept`, `handleAcceptAllTier1`, `handleAcceptHighConfidenceTier2` wrap their existing logic in commands.

### Keyboard shortcuts

- [ ] `Ctrl+Z` / `Cmd+Z` → `undoStore.undo()`
- [ ] `Ctrl+Shift+Z` / `Cmd+Shift+Z` / `Ctrl+Y` → `undoStore.redo()`
- [ ] Add to `KeyboardShortcuts.svelte`. Extend the "skip when typing" guard: currently checks `INPUT`, `TEXTAREA`, `SELECT`, but the manual redaction form uses Shoelace components whose internal elements may report different tag names. Also check `e.target.closest('sl-input, sl-textarea, sl-select')`.
- [ ] Register the shortcuts in the `?` help dialog.

### Toolbar buttons

- [ ] Optional but recommended: tiny Undo/Redo buttons (lucide `Undo2` / `Redo2`) in the bottom toolbar next to the zoom controls, visible only in Edit Mode. Disabled state when the respective stack is empty.

### Visual feedback

- [ ] On undo/redo, briefly flash the affected detection overlay(s) in `PdfViewer`. Pass `affectedDetectionIds` through a `flashDetection(ids)` export on the viewer, which adds a short-lived CSS class (e.g. `.overlay-flash`) that runs a 300 ms yellow-pulse animation and removes itself via `animationend`.
- [ ] CSS-only keyframes, no JS timers beyond the class toggle.
- [ ] For undo-of-create (the detection is being deleted), flash the about-to-disappear overlay **before** reversing, or briefly re-render a ghost overlay at the bbox. Pragmatic path: run the reverse after a 300 ms delay so the flash plays on the real overlay.

### Audit log behavior

- [ ] **The audit log is NOT rewound by undo.** Both the original action and its undo are recorded as separate entries.
- [ ] Add a new log line in the forthcoming `DELETE /api/detections/:id` handler: `detection.deleted` with detection id, document id, tier, entity type — no content. This matches the existing `detection.manual_created` / `detection.reviewed` log lines.
- [ ] Review-status reversals already go through `PATCH /api/detections/:id`, which already logs `detection.reviewed` on every call — so the undo of an accept naturally produces a second log entry. No change needed.

### Backend

- [ ] Add `DELETE /api/detections/{detection_id}` to `backend/app/api/detections.py`. Scope: delete any detection the authenticated proxy caller can see. No soft-delete — the detection row is removed. Audit log line as described above.
- [ ] Reject deletion if the detection's `source != 'manual'` **for now** — auto detections should be rejected, not deleted, so undo of an auto-detection accept still just flips the status. This keeps the manual-vs-auto boundary clean and prevents undo from destroying NER output the server produced.
- [ ] Update `backend/app/api/schemas.py` if any new response type is needed (likely just return 204 No Content).
- [ ] Add a frontend `deleteDetection(id)` in `frontend/src/lib/api/client.ts`.
- [ ] Add a `remove(id)` action to `detectionStore` that calls the API and splices the detection out of `allDetections`. `CreateManualCommand.reverse` calls this.

## Acceptance Criteria

- `Ctrl+Z` undoes the last manual redaction (text or area) by deleting it on the server and removing it from the overlay + sidebar
- `Ctrl+Z` undoes the last accept/reject/defer by restoring the previous `review_status`
- `Ctrl+Shift+Z` redoes what was just undone
- "Accept all Tier 1" and "Accept high-confidence Tier 2" batch actions undo as a single `Ctrl+Z` (single BatchCommand)
- Undo/redo buttons in the Edit Mode toolbar reflect stack state (enabled/disabled)
- Affected overlays flash yellow briefly on undo/redo
- Keyboard shortcuts are ignored while typing in the manual redaction form (including Shoelace inputs)
- Stack is per-document and cleared on navigation — no persistence across reloads
- Audit log contains both the original action and the undo as separate entries
- Server-side: `DELETE /api/detections/:id` exists, succeeds for `source: "manual"`, rejects with 409/422 for `source: "auto"` or `"regex"`, emits a `detection.deleted` log line with no content

## Not in Scope

- Persistent undo history across sessions (would require server-side command log — deliberate no)
- Collaborative undo / multi-user awareness
- Undo for boundary adjustment (#11), split/merge (#12), page complete (#10), search-and-redact batch (#09) — add those command types when their respective todos land; leave the command pattern extensible
