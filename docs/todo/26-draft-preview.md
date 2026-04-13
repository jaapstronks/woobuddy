# 26 — Draft Preview & Side-by-Side

- **Priority:** P2
- **Size:** M (1–3 days)
- **Source:** Draft Workflow briefing, "Draft preview" + "Side-by-side mode" sections
- **Depends on:** #25 (Document lifecycle — draft status)
- **Blocks:** #27 (Draft comments)

## Why

Before approving, the reviewer (or their supervisor) needs to see what the redacted document will actually look like. The draft preview renders redactions visually without permanently applying them — instant and reactive to changes.

## Scope

### Draft preview component (`<DraftPreview>`)

- [ ] Render PDF page via pdf.js from the locally-held PDF (IndexedDB / File API)
- [ ] Overlay black rectangles at accepted/auto-accepted detection coordinates (fetched from server as bbox metadata)
- [ ] Render article code as white text on each black rectangle
- [ ] Entirely client-side — PDF is local, detection bboxes come from server, preview is assembled in the browser
- [ ] Updates in real time as decisions change

### Access points

- [ ] Tab on document review page: "Beoordelen" / "Concept bekijken"
- [ ] Full-page view at `/app/dossier/[id]/draft/[docId]` for supervisors — supervisor must have the PDF loaded in their browser (client-first: the server cannot render a preview since it doesn't have the PDF)

### Side-by-side mode

- [ ] Split-screen: original on left, draft preview on right
- [ ] Synchronized scrolling and zoom
- [ ] Toggle: "Enkel" / "Naast elkaar"
- [ ] Falls back to tab toggle on narrow screens (<1200px)

## Acceptance Criteria

- Draft preview shows the document with black bars matching all accepted detections
- Changing a detection status immediately updates the preview
- Side-by-side mode scrolls both views in sync
- Supervisors can view the draft if they have the PDF loaded in their browser

## Not in Scope

- Draft comments on the preview (see #27)
- Server-side PDF generation for the preview (impossible under client-first — server doesn't have the PDF)
