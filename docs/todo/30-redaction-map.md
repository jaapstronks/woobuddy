# 30 — Redaction Map Generation

- **Priority:** P3
- **Size:** M (1–3 days)
- **Source:** Draft Workflow briefing, "What gets exported" section
- **Depends on:** #00 (Client-first architecture — generated during ephemeral export)
- **Blocks:** Nothing

## Why

A redaction map is an internal reference document showing the original PDF with colored overlays (not black bars) annotated with detection IDs and article codes. Useful for audit verification and for the reviewer to confirm redactions were applied correctly.

## Scope

- [ ] Generate companion PDF during the ephemeral export step: original document + colored rectangle annotations at each detection's coordinates — processed in memory alongside the redaction, streamed back with the redacted PDF
- [ ] Different fill colors per Woo article (e.g., blue for 5.1.2e, green for 5.1.1e)
- [ ] Text labels with detection IDs on each annotation
- [ ] Include in export options as a checkbox: "Lakkaart meenemen"
- [ ] PyMuPDF annotation rendering (not redaction — these are visual-only overlays) — done in the same in-memory pass, nothing stored server-side
- [ ] Alternative: generate the redaction map entirely client-side by overlaying colored rectangles on the pdf.js canvas (avoids sending the PDF to the server for this purpose)

## Acceptance Criteria

- Redaction map shows original content with colored annotations
- Each annotation has the article code and detection ID
- Colors are consistent per article across the document
