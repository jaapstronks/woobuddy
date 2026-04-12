# 12 — Search-and-Redact

- **Priority:** P1
- **Size:** L (3–7 days)
- **Source:** Editing briefing, "Feature 6: Search-and-Redact" section
- **Depends on:** #06 (Manual text redaction — reuses the article form)
- **Blocks:** Nothing

## Why

Woo documents can be hundreds of pages. When a reviewer spots a missed name on page 37, they shouldn't manually scroll through 200 pages to find the other 49 occurrences. Search-and-redact makes this a 10-second operation. This is one of the highest-value features for real reviewers.

## Assessment

The briefing's design is excellent. The cherry-pick + bulk-apply model is exactly right. The fuzzy matching suggestion (normalize, collapse, Dutch name-particle rules) is pragmatic.

**Adopt with simplification:** Start with exact match + basic normalization (case-insensitive, collapse whitespace). Add fuzzy Dutch name-particle matching as a P3 enhancement.

**Client-first bonus:** This feature becomes SIMPLER under client-first architecture. Since the PDF text is already extracted client-side (for NER submission), text search is a pure client-side string operation — no server round-trip needed for the search itself. Only the final "create detections" step talks to the server.

## Scope

### Search UI (fully client-side search)

- [ ] Search field in toolbar (or `Ctrl+F` opens it) with "Zoek & Lak" toggle
- [ ] Search runs against the client-side extracted text (from pdf.js `getTextContent()`) — no server call needed
- [ ] All occurrences highlighted in PDF with a distinct color (not detection highlight color)
- [ ] Sidebar shows list of all occurrences: page number, surrounding context (~40 chars)

### Match modes

- [ ] **Exact match** (default): case-insensitive, whitespace-normalized
- [ ] Toggle for fuzzy mode (future — for now, just exact)

### Bulk actions

- [ ] "Alles lakken" — opens article selector once, applies to all occurrences
- [ ] Cherry-pick: checkbox per occurrence, then apply to selected only
- [ ] Each created detection sent to server with: `source: "search_redact"`, `review_status: "accepted"`, bbox coordinates, article — NO `entity_text`

### Integration with existing detection system

- [ ] Search results that overlap with existing detections are indicated (already detected/redacted) — comparison done client-side by matching bboxes
- [ ] Newly created detections from search-and-redact appear in the sidebar and in the redaction log (server-side metadata)

## Acceptance Criteria

- Searching "Van der Berg" highlights all occurrences across all pages
- Reviewer can redact all at once with one article selection
- Reviewer can cherry-pick specific occurrences
- Created detections have `source: "search_redact"` and are audited

## Not in Scope

- Fuzzy Dutch name-particle matching ("v.d." / "vd" / "van den") — P3 enhancement
- Cross-document search-and-redact within a dossier — future feature
