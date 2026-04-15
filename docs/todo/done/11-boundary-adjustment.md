# 14 — Boundary Adjustment

- **Priority:** P2
- **Size:** L (3–7 days)
- **Source:** Editing briefing, "Feature 3: Boundary Adjustment" section
- **Depends on:** #05 (Mode toggle), #06 (Manual text redaction — for text layer mapping)
- **Blocks:** Nothing

## Why

System detections often have slightly wrong boundaries — too narrow (missing part of a name) or too wide (including surrounding text). Adjusting boundaries is faster than rejecting and re-creating.

## Scope

### Resize handles (area/single-line detections)

- [ ] Click existing detection in Edit Mode → enters edit state (blue border, corner/edge handles)
- [ ] Drag handles to resize the bbox
- [ ] 8 handles: 4 corners + 4 edges, 8x8px colored squares
- [ ] Appropriate cursors: `ew-resize`, `ns-resize`, `nwse-resize`, etc.

### Text-based boundary extension/shrink

- [ ] `Shift+click` on adjacent word → extend detection to include it
- [ ] `Alt+click` on edge word → shrink detection to exclude it
- [ ] `←`/`→` keys shrink/extend by one word when detection is in edit state
- [ ] `Alt+←`/`Alt+→` for character-level precision
- [ ] Live update of `bbox` coordinates (sent to server). Entity text display updates client-side from local text layer — server never stores text.

### Sidebar integration

- [ ] Edit state shows live preview of adjusted text with changes highlighted
- [ ] "Opslaan" button (or `Enter`) confirms adjustment
- [ ] `Escape` reverts to original boundaries

### Storage (client-first: bbox only)

- [ ] `review_status` changes to `"edited"`
- [ ] `original_bbox` preserved server-side for audit (coordinates only, no text)
- [ ] Audit log: original and new bbox coordinates, editor, timestamp — no text content
- [ ] Propagated detections: adjustment applies only to this instance (with option to propagate the adjustment too)

## Acceptance Criteria

- Drag handles resize detection overlays smoothly
- Shift+click extends text detection by one word
- Escape reverts all changes
- Adjusted detection retains link to original bbox for audit

## Not in Scope

- Adjusting multiple detections simultaneously
- Batch boundary adjustment
