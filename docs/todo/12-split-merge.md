# 15 — Split and Merge Detections

- **Priority:** P3
- **Size:** M (1–3 days)
- **Source:** Editing briefing, "Feature 4: Split and Merge" section
- **Depends on:** #05, #06, #11 (Boundary adjustment)
- **Blocks:** Nothing

## Why

Sometimes a detection spans two different types of sensitive info under different articles (needs split). Or adjacent detections should be one redaction (needs merge). These are real but infrequent scenarios — hence P3.

## Scope

### Split

- [ ] In Edit Mode, click detection → "Splitsen" button in sidebar
- [ ] Click a position within the detected text to define split point
- [ ] Text layer highlights the two resulting segments
- [ ] Two new detection cards appear, each independently editable
- [ ] Original detection replaced by the two new ones
- [ ] No modal, no extra confirmation — lightweight

### Merge

- [ ] `Ctrl+click` to select multiple detections in PDF or sidebar
- [ ] "Samenvoegen" button appears in toolbar
- [ ] Creates single detection spanning the combined area
- [ ] Keeps article/motivation from the first detection (editable)
- [ ] Individual detections removed, replaced by merged one

### Database (metadata only, no text content)

- [ ] `split_from` UUID field on detections (reference to original)
- [ ] `merged_from` JSON array of UUIDs on detections
- [ ] Split/merge operations update bbox coordinates on the server; text display is resolved client-side from local PDF

## Acceptance Criteria

- Split creates two functional detections from one, each with independent article/motivation
- Merge combines two adjacent detections into one
- Original detection IDs are preserved as references for audit

## Not in Scope

- Splitting area detections (text-only for now)
- Merging detections across pages
