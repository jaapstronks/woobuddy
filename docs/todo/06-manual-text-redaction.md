# 10 — Manual Text Selection Redaction

- **Priority:** P1
- **Size:** L (3–7 days)
- **Source:** Editing briefing, "Feature 1: Manual Text Selection" section
- **Depends on:** #05 (Mode toggle)
- **Blocks:** Nothing, but enriches #09 (Search-and-redact)

## Why

Automated detection will never be 100% complete. Reviewers must be able to select text in the PDF and redact it manually. This is the single most important editing feature — without it, the tool can't handle false negatives (missed BSNs, missed names), which are privacy breaches.

## Scope

### Text selection

- [ ] In Edit Mode, click-and-drag across PDF text layer to select text (native browser selection on pdf.js text layer spans)
- [ ] Selection snaps to word boundaries by default
- [ ] Hold `Alt` for character-level precision
- [ ] Selection can span multiple lines within a page (natural browser behavior)
- [ ] Selection cannot span pages (separate redactions per page)

### Floating action bar (`<SelectionActionBar>`)

- [ ] Appears near the selection on mouse-up (above or below, never obscuring)
- [ ] Contains "Lakken" (primary) and "Annuleren" (ghost) buttons
- [ ] Positioned via `getBoundingClientRect()` on the selection range, `position: fixed`
- [ ] Repositions on scroll
- [ ] Dismissed by clicking outside or pressing `Escape`
- [ ] `Enter` triggers "Lakken", `Escape` cancels

### Redaction form (inline, replaces floating bar)

- [ ] Woo article selector — dropdown grouped by tier, 5 most recently used articles pinned at top
- [ ] Entity type selector (optional) — pre-filled when article implies a type
- [ ] Motivation text — template pre-filled from selected article, editable
- [ ] "Bevestigen" button to confirm

### Storage (client-first: server stores metadata only)

- [ ] New detection record sent to server with: `source: "manual"`, `review_status: "accepted"`, tier, article, **bounding box coordinates** — but NO `entity_text`
- [ ] The `entity_text` is only held client-side (derived from the local PDF's text layer) for display purposes
- [ ] PDF overlay updates: black bar with article code on the selected text
- [ ] Detection appears in sidebar list
- [ ] Audit log entry: who added what (detection ID, article, type), when — no text content

### DOM-to-text mapping (simplified under client-first)

- [ ] Map selected text layer `<span>` elements to bounding box coordinates using `getBoundingClientRect()` and the pdf.js viewport transform
- [ ] No need to reconcile with PyMuPDF extraction — the text layer IS the source of truth under client-first architecture
- [ ] Resolve multi-line selection to one or more bounding boxes
- [ ] Store the selected text client-side (IndexedDB or in-memory) for display in the sidebar; send only the bbox to the server

## Acceptance Criteria

- Reviewer can select text in Edit Mode, assign an article, and see it appear as a redaction
- The new detection is stored on the server with bbox, article, type — but NOT `entity_text`
- The sidebar shows the entity text by reading it from the client-side PDF text layer
- Word-boundary snapping works; Alt overrides to character level
- Floating bar positions correctly and doesn't obscure the selection

## Not in Scope

- Area selection for non-text content (see #07)
- Boundary adjustment of existing detections (see #11)
