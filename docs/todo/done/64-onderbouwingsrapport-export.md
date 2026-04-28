# 64 — Onderbouwingsrapport export (audit log as Woo-besluit bijlage)

- **Priority:** P2
- **Size:** M (1–3 days)
- **Phase:** C (polish & launch-ready)
- **Status:** **Shipped 2026-04-28** on `feat/audit-log-onderbouwingsrapport`. Built client-side via `pdf-lib`; lazy-loaded behind the toolbar button so the landing-page bundle is unaffected. Branding follows the recommended default (small monochrome wordmark in the footer, no logo on the cover); reviewer signature line deferred per the open-question recommendation.
- **Source:** Roadmap promise on `/(hosted)/roadmap` — *"Audit-log en onderbouwingsrapport. Per gelakte passage de juridische grond en motivering, exporteerbaar als bijlage bij het Woo-besluit."* Plus the trust-story discussion 2026-04-28 (the existing JSON debug export is a developer aid, not a defensible archive artifact).
- **Depends on:** #00 (client-first), #19 (redaction log — same data source), #48 (accessible PDF export — same XMP/PDF/A-2b post-processing pipeline can be reused for the report PDF if we go server-route).
- **Blocks:** Nothing.

## Why

We already have two artifacts that *contain* the redaction motivation:

1. The in-app **redaction log table** at `/review/[docId]/log` (#19) — great for live oversight, useless as a filed attachment.
2. The **`redaction-log.csv`** inside the DiWoo publication zip (#52) — machine-readable, but hostile to a jurist who has to read it during a bezwaarprocedure.
3. (And the `*.detections.json` debug dump in `debug-export.ts` — explicitly framed as a dev triage aid, not for archiving.)

None of those is what a Woo-coördinator actually needs to attach to the **Woo-besluit**: a human-readable PDF, in Dutch, that explains for each redaction *why* it was made, with enough provenance that someone reading it months later can verify the file matches the redacted PDF they have in their dossier.

This todo cashes in the roadmap promise by producing exactly that document. It strengthens the trust story without changing the architecture — all the data is already in memory on the review screen.

**Distinct from the existing artifacts:**

| Artifact | Format | Audience | Purpose |
|---|---|---|---|
| `/review/[docId]/log` (#19) | HTML in-app | Reviewer / supervisor (live) | Oversight + bulk revision during review |
| `redaction-log.csv` (#52) | CSV inside diwoo zip | DiWoo / GPP-Woo ingest pipeline | Publication metadata for open.overheid.nl |
| `*.detections.json` debug dump | JSON | Developer | Triage false positives / regression hunting |
| **#64 onderbouwingsrapport** | **PDF (+ optional CSV)** | **External recipient of Woo-besluit** | **Defensible bijlage** explaining each redaction with provenance |

## Scope

### Trigger and placement

- [ ] New button in the review toolbar next to the existing "Lakken & exporteren" — labelled **"Onderbouwingsrapport"**, secondary styling so it doesn't compete with the primary export.
- [ ] Disabled with a tooltip until at least one detection is in `accepted` or `auto_accepted` state.
- [ ] Available independently of the redacted-PDF export — a reviewer should be able to download the report on its own (re-export after an addendum) without re-running redaction.
- [ ] When the user has just exported a redacted PDF, the post-export panel offers "ook onderbouwingsrapport downloaden" as a one-click follow-up so the two files end up in the same dossier.

### Report content (PDF)

Single PDF, A4 portrait, Dutch, professional but not branded-heavy. Sections:

- [ ] **Voorblad**: title "Onderbouwing van redacties", document filename, page count, total redaction count, generation timestamp (UTC + Europe/Amsterdam).
- [ ] **Provenance block**:
  - SHA-256 of the original uploaded PDF bytes
  - SHA-256 of the redacted PDF (only included if the report is generated *after* a successful redaction export in the same session — otherwise omitted with an explicit "redactie nog niet geëxporteerd" line)
  - WOO Buddy version (frontend git commit short hash, surfaced via Vite env var)
  - Optional reviewer-supplied fields: zaaknummer, reviewer naam, opmerkingen — a small form before generation, all optional, all stored only in memory
- [ ] **Samenvatting**: counts by Woo-article, counts by tier, counts by source (auto vs manual), counts by entity type — same numbers the in-app stats bar shows.
- [ ] **Per-redactie tabel**: one row per accepted detection, in document order. Columns: nummer, pagina, type (Dutch label), Woo-artikel (code + grond), bron (auto/handmatig), motivatie (templated Dutch sentence keyed off the article). Long tables paginate with repeated headers.
- [ ] **Bijlage A — Toelichting per Woo-grond**: short Dutch description of each article that appears in the report, taken from `WOO_ARTICLES[code].description`. Helps the recipient who isn't a Woo-jurist read the table.
- [ ] **Footer on every page**: "Gegenereerd met WOO Buddy — uw PDF heeft uw browser nooit verlaten" + page X / Y.

### Explicitly out of scope (client-first)

- [ ] **No entity text in the report.** Same constraint as #19 / #52. The recipient already has the redacted PDF in their hands; the report tells them *why* each black bar exists, not *what* was behind it.

### Provenance hashes — implementation

- [ ] Compute SHA-256 client-side via `crypto.subtle.digest` over the original PDF `ArrayBuffer` already held in memory by the review page. Cache on the review-state store so it's not recomputed on every "Onderbouwingsrapport" click.
- [ ] When the report is generated *after* a redaction export in the same session, also hash the redacted blob returned by `exportRedactedPdf` and include it. If the user generates the report before exporting, omit this field with explicit copy ("redactie nog niet geëxporteerd — hash niet beschikbaar"). Don't fake it.
- [ ] Display hashes as `sha256:<lowercase-hex>` with a copy-to-clipboard affordance in the UI provenance panel as well, so reviewers can verify them out-of-band.

### PDF generation

- [ ] **Decision needed:** client-side (`pdf-lib`, ~250KB gzip, MIT — fits client-first) vs server-side (reuse the FastAPI + PyMuPDF pipeline already on the box for #48).
- [ ] **Recommendation:** start client-side with `pdf-lib`. The report contains zero document content (no extracted text, no bbox snippets), so client-side has no architectural payoff over server-side — but it keeps the "uw PDF verlaat nooit uw browser" line literally true even for the report, and avoids a new server route. The bundle-size cost is acceptable; lazy-load the report module behind the toolbar button so it doesn't hit the landing-page LCP.
- [ ] If `pdf-lib` ergonomics fight us on table layout, fall back to **HTML → PDF via `window.print()`** with a hidden iframe and a print stylesheet. Crude, zero deps, surprisingly good for tabular content. Not a long-term path, but a fine escape hatch.
- [ ] Whichever path, the file is generated entirely in the browser; nothing new is sent to the server.

### Optional secondary CSV

- [ ] Reuse `buildRedactionLogCsv` (already in `frontend/src/lib/services/diwoo/csv.ts`) and offer a **CSV alongside the PDF** in the same download trigger — same data, machine-readable, useful for archives that prefer structured formats. No new code path; just call the existing builder and bundle alongside the PDF in a small zip if both are requested.
- [ ] If only PDF is wanted (likely default), download the bare PDF without zipping — one file is friendlier than a zip.

### Filename convention

- [ ] PDF: `onderbouwing_<original-filename-without-ext>_<YYYY-MM-DD>.pdf`
- [ ] If both PDF + CSV: `onderbouwing_<original-filename-without-ext>_<YYYY-MM-DD>.zip`
- [ ] Mirror the existing `gelakt_*.pdf` convention so the two files file together alphabetically in a dossier folder.

### Analytics

- [ ] Plausible event `onderbouwing_export_completed` with the same buckets we already use for `export_completed` (`redaction_bucket`, `page_bucket`). No new event categories.
- [ ] No event payload contains anything that could fingerprint a document (per `frontend/src/lib/analytics/plausible.ts`).

### Roadmap page update

- [ ] Move the "Audit-log en onderbouwingsrapport" bullet on `frontend/src/routes/(hosted)/roadmap/+page.svelte:91` from "Hierna" to a new "Recent gebouwd" section (or strike it through and link to the feature) once shipped. The roadmap page is a public commitment device; let it reflect reality.

## Acceptance criteria

- [ ] Toolbar button generates and downloads a PDF report for any document with ≥1 accepted detection.
- [ ] PDF opens cleanly in Acrobat, Preview, and a Chrome built-in viewer; tables paginate correctly across page breaks.
- [ ] Provenance block shows the original-PDF SHA-256; redacted-PDF SHA-256 appears only when a redaction export has happened in the same session.
- [ ] No `entity_text` (or any extracted document text) appears anywhere in the report. Verified by spot-checking generated PDFs against fixture documents in `frontend/tests/fixtures/`.
- [ ] Per-row motivation strings match the Dutch grond labels in `WOO_ARTICLES`.
- [ ] Bundle size impact: report module is lazy-loaded; landing page bundle increases by ≤2KB (the trigger import only).
- [ ] Plausible `onderbouwing_export_completed` fires with bucketed counts; no document-identifying payload.
- [ ] Roadmap page updated to reflect the shipped state.

## Open questions

- **Branding / letterhead:** does the report carry a small WOO Buddy mark in the header, or is it deliberately neutral so a gemeente can hand it out without it looking like an ad? **Recommended default:** small monochrome wordmark in the footer only, no logo on the cover. Reviewers can override if a pilot asks.
- **Reviewer signature line at the bottom:** in scope or not? **Recommended:** out of scope for v1 — adding a "geparafeerd door" line implies non-repudiation we don't actually provide (anyone can type a name into the form). Revisit when there's an authenticated user model (Phase E).
- **Hash chain across re-exports** (#28 export-versioning territory): explicitly out of scope here — the report describes the redactions *as exported in this session*. Versioning across multiple exports is #28's problem.

## Not in scope

- Server-side storage of the report (everything is ephemeral, like the rest of the export pipeline).
- Including extracted text snippets (would require keeping `entity_text` in detections — violates #00).
- Digital signatures / qualified e-signatures on the report PDF — possible future Enterprise feature, not here.
- Multi-document / dossier-level reports — single document only, like the rest of the app today (see `CLAUDE.md` "Single-document flow").
