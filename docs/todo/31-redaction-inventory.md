# 31 — Redaction Inventory (CSV/XLSX)

- **Priority:** P3
- **Size:** S (< 1 day)
- **Source:** Draft Workflow briefing, "What gets exported" section
- **Depends on:** #19 (Redaction log — same data, different output format)
- **Blocks:** Nothing

## Why

A machine-readable spreadsheet of all redaction decisions is useful for audit, reporting, and integration with other systems. It's the redaction log in portable form.

## Scope

- [ ] Export button on redaction log: "Exporteer als CSV" / "Exporteer als XLSX"
- [ ] Columns match the redaction log metadata: document, page, **type** (not passage text — client-first), tier, article, status, source, reviewer, date, motivation (generic template)
- [ ] **No entity text column** — the server doesn't store it. If the user needs entity text in the inventory, it must be composed client-side by joining detection bboxes with locally-extracted text before generating the spreadsheet
- [ ] Option A: generate client-side using a JS XLSX library (SheetJS/xlsx) — preferred since it can include entity text from local PDF
- [ ] Option B: generate server-side with `openpyxl` — metadata only, no entity text
- [ ] Include in dossier-level export as a checkbox option

## Acceptance Criteria

- CSV/XLSX download from redaction log page
- All columns present and correctly populated
- Included in dossier export ZIP when selected
