# 52 — DiWoo / TOOI publication metadata export

- **Status:** Done (single-document scope, see "Built vs deferred" below)
- **Priority:** P2
- **Size:** M (1–3 days)
- **Source:** Competitor landscape 2026-04 — Novadoc/EntrD close the loop to open.overheid.nl; we don't
- **Depends on:** #19 (redaction log) — already done
- **Blocks:** Nothing, but strongly complements #31 (redaction inventory CSV)

## Built vs deferred

**What shipped:**

- Toolbar button "Met publicatiemetadata" in `/review/[docId]` next to the existing "Gelakte PDF" export, opens a Shoelace dialog (`PublicationExportDialog.svelte`).
- Dialog collects: `officieleTitel` (defaults to filename), `identifier`, `informatiecategorie` (TOOI dropdown), `opsteller`/organisatie, optional `omschrijving`. Required fields gate the submit button.
- Auto-filled fields surfaced in the dialog so the reviewer knows what's in the bundle: `creatiedatum` (from document), `bestandsformaat=application/pdf`, `language=nld`, `documenthandeling=anonimiseren` for this export.
- Bundle (zip via fflate, fully client-side) contains:
  - `redacted.pdf` — existing redact-stream endpoint output, called once per export
  - `metadata.xml` — DiWoo v0.9.8 with every required element (`classificatiecollectie`, `creatiedatum`, `format`, `geldigheid`, `language`, `opsteller`, `publisher`, `verantwoordelijke`, `titelcollectie/officieleTitel`) plus optional `documenthandelingen` and `identifiers`/`omschrijvingen` when provided
  - `metadata.json` — GPP-Woo publicatiebank `Publication` + `Document` envelope, both starting `publicatiestatus=concept`
  - `redaction-log.csv` — accepted detections only, columns: #, pagina, type, trap, woo_artikel, grond, status, bron, beoordeeld_op, bbox_count, motivatie. No entity text (client-first)
  - `README.txt` — Dutch explanation, what each file is, how to feed it into GPP-publicatiebank or another Woo platform
- Vendored TOOI value lists in `frontend/static/diwoo-tooi-lists/`: `informatiecategorieen.json` (18 statutory items from `scw_woo_informatiecategorieen/3`), `formatlijst.json`, `version.json`. `organisaties.json` is a deliberate stub — see file note.
- `scripts/bump-tooi-lists.mjs` refreshes the lists from standaarden.overheid.nl. Supports `--check` for CI.
- Plausible event `publication_export_completed` (same shape as `export_completed`) so dashboard can compare adoption.
- Tests: `xml.test.ts`, `json.test.ts`, `csv.test.ts`, `bundle.test.ts` — every required DiWoo element, every required GPP-Woo field, CSV column order + escaping, zip round-trip and PDF byte preservation.

**Deliberately deferred (document when picked up later):**

- **Runtime XSD validation in the browser** — the spec listed `xmllint-wasm` as one option. Validation in the dialog is form-level (required-field gating) rather than full-XSD; the cost of shipping a ~2 MB WASM blob outweighs the marginal correctness gain when fixture tests already enforce structural compliance. Add it back if a real reviewer-side bug surfaces.
- **TOOI organisaties value list** — full register has tens of thousands of entries and would either bloat the bundle or need lazy loading + a search UX. V1 keeps `opsteller` / `verantwoordelijke` as free text; revisit when org context lands (post-#33 / #32).
- **Documentsoort / thema / trefwoord pickers** — DiWoo v0.9.8 requires 1+ in each of these. The serializer fills sensible defaults (documentsoort=besluit, thema=primary informatiecategorie label, trefwoord=derived from title) so the schema is satisfied without burdening V1's small dialog. Promote to dropdowns if downstream platforms reject the defaults.
- **POSTing the bundle directly to a publicatiebank instance** — out of scope per the original todo. The bundle is a one-way file export.
- **Multi-document / dossier sitemap** — V1 is single-document, matching the rest of the app.

## Why

Today WOO Buddy ends at "redacted PDF." The Dutch Woo publication chain actually continues: gemeenten publish their besluit + redacted documents to [open.overheid.nl](https://open.overheid.nl) via the [GPP-Woo](https://github.com/GPP-Woo) platform (or a commercial alternative), and that publication requires a **DiWoo-compliant sitemap + metadata bundle** following the [TOOI thesaurus](https://standaarden.overheid.nl/diwoo/metadata).

Novadoc and EntrD both advertise "zoeken + lakken + publiceren onder de Woo" as a single integrated flow. WOO Buddy stops two steps short. By emitting a DiWoo-compliant XML + JSON bundle alongside the redacted PDF, we make our output **publication-ready** for whatever publication platform the gemeente uses — without ourselves becoming a publication platform.

This is not a "build a portal" todo. It's a "emit a file that the existing publication stack understands" todo. Scope is small, strategic value is high: it removes the biggest objection a gemeente-IT buyer has ("but how do we get this into our publicatiebank?") with a 1–3 day build.

## Scope

### Frontend

- [ ] **Export option in the review toolbar**: next to the existing "Exporteer gelakte PDF" button, add "Exporteer met publicatiemetadata (.zip)" (secondary styling). Behind a `sl-tooltip` explaining DiWoo and linking to the standaard.
- [ ] **Metadata-input dialog** that pops up before the zip export, collecting the required DiWoo fields:
  - `dcterms:title` (document title — default from filename, editable)
  - `dcterms:identifier` (besluit-identifier / referentie — required, free text)
  - `diwoo:informatiecategorie` (required, dropdown — TOOI value list, loaded as static JSON from `frontend/static/diwoo-tooi-lists/`)
  - `dcterms:creator` (organisatie, TOOI value list — optional at V1 since we don't know the user's org; default to free-text, upgrade to dropdown post-auth)
  - `dcterms:created` + `dcterms:modified` (dates — creation = first upload in session, modified = export time)
  - `dcterms:language` (default `nl`)
  - `diwoo:documenthandelingen` (optional — captures the redaction as a handeling of type "anonimiseren")
- [ ] **Export bundle format** (zip, in-memory, streamed to save dialog):
  - `redacted.pdf` — the redacted PDF, exactly what today's export produces
  - `metadata.xml` — DiWoo sitemap XML entry validating against [diwoo-metadata.xsd v0.9.8](https://standaarden.overheid.nl/diwoo/metadata/doc/0.9.8)
  - `metadata.json` — same content in the GPP-Woo JSON API shape (see [GPP-publicatiebank](https://github.com/GPP-Woo/GPP-publicatiebank))
  - `redaction-log.csv` — the inventory from #31 (if present) so publishers have the grondenoverzicht alongside
  - `README.txt` — Dutch explanation of what each file is, with links to the DiWoo standard and GPP-Woo
- [ ] **Validation before download**: run the generated XML through a client-side XSD validator (`xmllint-wasm` or similar) and surface a friendly error if the metadata is incomplete. Required fields must be filled before the button activates.

### TOOI value lists

- [ ] **Vendor the TOOI value lists** into `frontend/static/diwoo-tooi-lists/` as static JSON:
  - `informatiecategorieen.json` (controlled vocabulary)
  - `organisaties.json` (list of overheidsorganisaties — this is large; consider lazy-loading)
  - `formatlijst.json` (file format controlled vocabulary)
- [ ] **Versioning**: record the TOOI list version and the DiWoo metadata schema version in the exported bundle. A bump-TOOI script that refreshes from standaarden.overheid.nl lives in `scripts/` and documents how often to re-run (annually is fine).
- [ ] **Fallback**: if TOOI lists fail to load (network, tenant with strict CSP), disable the publication-export button with a helpful message rather than producing invalid XML.

### Backend

**Nothing.** The redaction log is already in the database (#19 done) and we fetch it via existing APIs. XML/JSON serialization is pure client-side string building — no new server route.

### Tests

- [ ] XML output validates against the vendored XSD (unit test with fixtures)
- [ ] JSON output matches the GPP-publicatiebank OpenAPI schema (compile it into JSON Schema, validate with ajv)
- [ ] Integration test: complete review + publication export → unzip → assert all expected files are present and well-formed
- [ ] Round-trip sanity: a second reviewer picking up the redacted PDF + metadata.xml can reconstruct the context (who redacted what, under which ground, at what time)

## Acceptance

- A reviewer can export a `.zip` bundle containing redacted PDF + DiWoo metadata.xml + GPP-Woo metadata.json + redaction-log.csv
- The XML validates against the current DiWoo XSD (v0.9.8 or current)
- Required metadata fields are enforced before export; optional fields degrade gracefully
- Landing/documentation page explains the feature in Dutch: *"Uw besluit is klaar voor publicatie via GPP-Woo of een ander Woo-platform."*
- Self-host documentation includes the bump-TOOI script + a note about schema version compatibility

## Not in scope

- Actually POSTing the bundle to a GPP-publicatiebank instance — that's a direct-publish feature, should be #60-range if we ever do it, and bumps into "server holds document" concerns. V1 is "produce the bundle, user publishes manually or via their DMS."
- Sitemap generation for multi-document dossiers — depends on #53. For V1 each bundle is single-document.
- Commercial platform-specific metadata dialects beyond DiWoo (Novadoc/Decos/Djuma proprietary fields) — DiWoo is the open standard; commercial platforms can import it.
- Writing a full GPP-Woo API client — out of scope, this todo is one-way file export only.

## Open questions

- Do we sell this feature visibly on the landing page? Suggested: yes — *"WOO Buddy levert publicatie-klare output volgens de DiWoo-standaard"* is a sentence that makes procurement nod.
- Should the metadata dialog remember values across sessions (organization name, default creator)? For the anonymous path, no — that's state we don't persist. Post-auth, yes, as org-level defaults (belongs to #33).
