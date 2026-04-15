# 28 — Export Versioning & Re-Export

- **Priority:** P2 — blocked on team-pilot demand signal (see README Phase F)
- **Size:** M (1–3 days)
- **Source:** Draft Workflow briefing, "Re-Export" section
- **Depends on:** #00 (Client-first architecture — exports are ephemeral), #25 (Document lifecycle), **and a real team pilot asking for it**
- **Blocks:** Nothing

> **Do not start this before Phase D's public launch + validation decision gate.** Re-export audit trails are a compliance feature for teams that publish Woo-besluiten — individual reviewers just export the file and save it themselves. See README "GTM & launch sequencing."

## Why

Woo processing is iterative. After export, a decision may be challenged or new information surfaces. The previous export must be invalidated and a new version generated. Without versioning, there's no audit trail of what was published when.

**Client-first impact:** Under client-first, exports are ephemeral — the PDF is streamed to the server, redacted in memory, and streamed back. The server never stores the redacted PDF. But we DO store **export metadata** (version number, timestamp, who exported, detection snapshot) to track what decisions were in effect at each export. The actual PDF files are the user's responsibility to save locally.

## Scope

### Exports table (metadata only — no stored PDFs)

- [ ] New `exports` table: `id`, `dossier_id`, `document_id` (null for dossier-level), `version` (1, 2, 3...), `format` (concept/definitief), `detection_snapshot` (JSONB: all detection states at export time — bbox, type, article, status — NO entity text), `created_at`, `created_by`, `is_current`
- [ ] No `storage_key` — under client-first, the redacted PDF is streamed directly to the user's browser for download, not stored in MinIO

### Version management

- [ ] On re-export: set `is_current = false` on previous records, create new with `is_current = true`
- [ ] Previous exports are not re-downloadable from the server (the server doesn't have the PDF) — the user must have saved the file locally
- [ ] Reopening a document invalidates the current export metadata record

### Change summary

- [ ] Compare detection snapshots between versions
- [ ] Generate summary: "Versie 2: 3 lakkingen toegevoegd, 7 verwijderd, 2 aangepast t.o.v. versie 1"
- [ ] Store in audit log, optionally include in motivation report

### Export history UI (`<ExportHistory>`)

- [ ] List all export versions for a document/dossier (metadata only)
- [ ] Each entry: version number, date, format, who generated it, change summary
- [ ] No download links for past versions (the server doesn't store the PDFs — user must have saved locally)
- [ ] Clear messaging: "Download je gelakte documenten direct na export. WOO Buddy slaat geen documenten op."

### API endpoints

- [ ] `GET /api/documents/:id/exports` — list all export version metadata
- [ ] `GET /api/dossiers/:id/exports` — same, dossier level
- [ ] `POST /api/export/redact` — ephemeral: accepts PDF stream + detection bboxes, returns redacted PDF stream (see #00)

## Acceptance Criteria

- Re-exporting creates version 2 metadata and marks version 1 as outdated
- Change summary accurately lists additions, removals, modifications (based on detection snapshots)
- Export history shows all versions with metadata (no re-download — that's by design)
- User receives the redacted PDF as a direct download in their browser
