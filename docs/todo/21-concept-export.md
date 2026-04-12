# 22 — Concept Export with Watermark

- **Priority:** P2
- **Size:** S (< 1 day)
- **Source:** Draft Workflow briefing, "When to export" section
- **Depends on:** #00 (Client-first architecture — export is ephemeral streaming)
- **Blocks:** Nothing

## Why

Draft exports must be visually distinct from final exports to prevent accidental publication. A watermark makes it immediately obvious that a document is not the final version.

## Scope

- [ ] Export dialog offers two formats: "Concept" (draft) and "Definitief" (final, only for approved docs)
- [ ] Concept export: during the ephemeral `/api/export/redact` call, PyMuPDF applies diagonal "CONCEPT — Niet definitief" watermark on each page in the same in-memory pass as the redaction
  - Light gray, large font, rotated 45 degrees
  - Single PyMuPDF operation per page, no additional disk I/O
- [ ] Definitief export: clean, no watermark — only available for documents with "approved" status
- [ ] Export dialog clearly indicates which format is available based on document status
- [ ] Both formats stream the result directly to the browser as a download — nothing stored server-side

## Acceptance Criteria

- Concept export has visible watermark on every page
- Final export has no watermark and is only available for approved documents
- Both formats generate valid, downloadable PDFs
