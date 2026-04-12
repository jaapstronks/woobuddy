# 11 — Area Selection Redaction

- **Priority:** P1
- **Size:** M (1–3 days)
- **Source:** Editing briefing, "Feature 2: Area Selection" section
- **Depends on:** #05 (Mode toggle), #06 (Manual text redaction — reuses the article form)
- **Blocks:** Nothing

## Why

Not all sensitive content is text. Signatures, photos, handwritten annotations, tables with embedded fonts, or scanned pages within a digital PDF need redaction too. Area selection covers everything text selection can't.

## Scope

### Interaction

- [ ] In Edit Mode, hold `Shift` + drag to draw a rectangle on the PDF page
- [ ] Semi-transparent rectangle visible while dragging
- [ ] On mouse-up, same floating action bar appears ("Lakken" / "Annuleren")
- [ ] Same article form as text selection

### Coordinate handling

- [ ] Convert canvas coordinates to PDF coordinates using the current viewport transform (zoom, scroll offset)
- [ ] Store as `bbox` (x0, y0, x1, y1) without associated text
- [ ] Detection record: `entity_type: "area"` (no `entity_text` field under client-first — the server never stores text content)

### Display

- [ ] Area redactions render as filled rectangles in the PDF overlay
- [ ] Sidebar shows area detections as "Handmatig geselecteerd gebied"

### Storage (client-first: server stores metadata only)

- [ ] Same as manual text redaction: `source: "manual"`, `review_status: "accepted"`, bbox coordinates sent to server — no content
- [ ] Audit log entry records the area selection (detection ID, type, page — no content)

## Acceptance Criteria

- Shift+drag draws a rectangle on the PDF
- Rectangle converts correctly to PDF coordinates at any zoom level
- Area detection appears in sidebar and renders as an overlay
- Works for signatures, images, and content where text selection fails

## Not in Scope

- OCR on selected areas (future enhancement)
- Auto-detecting image regions
