# 48 — Accessible PDF Export (Language Tag, XMP, Accessible Redaction Marks, PDF/A-2b)

- **Priority:** P1
- **Size:** M (1–3 days)
- **Source:** Accessibility improvements plan 2026-04
- **Depends on:** Nothing
- **Blocks:** Nothing

## Why

Dutch government content falls under **digitoegankelijk.nl / EN 301 549 / WCAG 2.1 AA**, and published PDFs are expected to conform to PDF/UA-1 and PDF/A for archival. Most gelakte Woo besluiten in the wild fail this hard — they are visual-only PDFs with no language tag, no structure, and black rectangles that give screen reader users nothing but a gap in the text.

WOO Buddy's current export (`backend/app/services/pdf_engine.py:413` — `apply_redactions`) has the same problems:

1. **No language tag** on the document catalog. Dutch TTS picks the wrong voice.
2. **No XMP metadata** — no title, no producer, no description.
3. **Redaction overlay is white-on-black 6pt text** (`pdf_engine.py:441`) — not exposed as accessible text to screen readers. A screen reader user does not know *why* a passage is gelakt.
4. **No PDF/A conformance** — not archivable under Dutch gemeentelijke DMS standards.
5. **No alt text** on redaction marks.
6. **Outlines / bookmarks** are preserved by PyMuPDF default, but this is not verified by tests.

Being the tool that produces **accessible, archive-compliant** redacted PDFs is a real differentiator for the government audience — it turns a compliance headache into a feature bullet point. It is the kind of thing that can go on the landing page next to "uw PDF verlaat uw browser niet": *"...en wat eruit komt voldoet aan WCAG en PDF/A."*

This todo intentionally scopes **PDF/UA-1 full conformance OUT**. Generating a correct structure tree from a flat source PDF is a genuinely hard problem — it requires either a tagged source document (which #46 enables, because LibreOffice can emit tagged PDFs from structured `.docx`) or a commercial SDK that conflicts with the open-source story (#43). The honest answer is: do the Tier 1 + Tier 2 wins now, document the PDF/UA-1 gap, and revisit once #46 is producing tagged sources.

## Scope

### Tier 1 — low-cost, high-impact (do first)

- [ ] **Set `/Lang (nl-NL)` on the document catalog** via `pikepdf` as a post-processing step after PyMuPDF redaction. Two lines of code. Instantly makes Dutch TTS work in Acrobat Reader, NVDA, JAWS, VoiceOver.
- [ ] **Write XMP metadata** via `pikepdf`:
  - `dc:title` — user-editable, defaults to the uploaded filename stem
  - `dc:language` — `nl-NL`
  - `dc:description` — auto-generated one-liner from the redaction log: e.g. *"Gelakt conform Art. 5.1.2.e en 5.1.2.i — 2026-04-15"*
  - `pdf:Producer` — `WOO Buddy`
  - `xmp:CreatorTool` — `WOO Buddy` + version
  - `xmp:CreateDate` — export timestamp
- [ ] **Replace the 6pt white-on-black overlay text with an accessible annotation.** Instead of drawing text *inside* the black rectangle (which is a painted graphic, not accessible text), attach the article reference as the redaction annotation's `/Contents` field and `/Alt` property. Screen readers then announce *"Gelakt — Artikel 5.1.2.e persoonsgegevens"* where sighted users see a black box. **This single change closes the biggest accessibility gap in Dutch Woo besluiten today.**
  - Implementation: after `apply_redactions`, walk the resulting PDF with `pikepdf`, add a `Square` or custom annotation on top of each redacted rectangle with `/Contents` = Dutch article description and `/Alt` matching. Or: keep PyMuPDF's redaction rectangle but add a parallel accessible annotation via `pikepdf`.
  - The article description mapping lives alongside the existing Woo article list — Dutch text like "Artikel 5.1.2.e — persoonsgegevens", "Artikel 5.1.1.c — veiligheid van de staat", etc.
- [ ] **Preserve source outline (bookmarks)** — verify PyMuPDF's default behaviour via a test fixture with bookmarks in the source PDF. Add a regression test.
- [ ] **User-editable title field** on the export screen in the frontend: an `sl-input` with the default filename stem, used as XMP `dc:title`. Optional — user can leave it blank and we'll use the filename.

### Tier 2 — PDF/A-2b conformance

- [ ] **Post-process with Ghostscript** to produce PDF/A-2b:
  ```
  gs -dPDFA=2 \
     -dPDFACompatibilityPolicy=1 \
     -sProcessColorModel=DeviceRGB \
     -sDEVICE=pdfwrite \
     -dBATCH -dNOPAUSE -dQUIET \
     -sOutputFile=out.pdf in.pdf
  ```
  - Ghostscript is GPL, widely deployed, and acceptable for open-source self-host. Add to backend Docker image (~50 MB).
  - Runs as a subprocess in a `finally`-cleaned tempdir, same pattern as the #46 LibreOffice path.
  - Font embedding, color space normalization, and XMP metadata preservation are all handled by Ghostscript.
- [ ] **veraPDF validation in CI**: add the open-source veraPDF CLI as a test dependency. A small fixture set in `backend/tests/fixtures/accessibility/` runs through the full export pipeline and must validate as PDF/A-2b. Catches regressions when we touch the redaction code.
- [ ] **Graceful degradation**: if Ghostscript is unavailable (self-hosters who skipped the dependency), the export still works and produces a non-PDF/A file with a log warning. PDF/A is an *enhancement*, not a blocker.

### Tier 3 — PDF/UA-1 (EXPLICITLY OUT OF SCOPE)

Do **not** attempt this in this todo. Document the decision in the README of this todo's done file when it moves to `done/`. The path to PDF/UA-1 runs through:

- Properly tagged source PDFs (enabled by #46 — LibreOffice produces tagged PDFs from structured .docx)
- Preserving the structure tree through redaction (PyMuPDF's `apply_redactions` drops it, so a pikepdf workaround is needed)
- Linking each redaction annotation into the structure tree as a proper element

Revisit as a follow-up todo once #46 is shipping and we have real tagged source PDFs to work with.

### Tier 4 — machine-readable redaction inventory (stretch)

- [ ] If time permits: embed a JSON redaction inventory as a PDF/A-3 file attachment. Structure: `[{page, bbox, article, rationale}, ...]`. Aligns with #19 (redaction log) and the deferred #31 (redaction inventory CSV/XLSX). Verifying parties can programmatically check which passages were redacted and under which article.
- [ ] If this turns out to need Tier 3 plumbing, skip it and carve out a follow-up todo.

### Backend implementation

- [ ] New module `backend/app/services/pdf_accessibility.py`:
  - `add_language_tag(pdf_bytes, lang="nl-NL") -> bytes`
  - `write_xmp_metadata(pdf_bytes, title, description, ...) -> bytes`
  - `add_accessible_redaction_annots(pdf_bytes, redactions) -> bytes`
  - `convert_to_pdfa(pdf_bytes) -> bytes` (Ghostscript wrapper with graceful fallback)
- [ ] Thread these into the export flow (`backend/app/api/export.py`) as post-processing steps after `apply_redactions`. Order: apply_redactions → add_accessible_redaction_annots → add_language_tag → write_xmp_metadata → convert_to_pdfa.
- [ ] No logging of title strings or document content in these steps (consistent with the client-first logging rule).
- [ ] Performance budget: the whole post-processing chain should add < 2s for a typical 50-page document. Measure in CI.

### Frontend

- [ ] **Optional title field** on the export screen in the review UI — `sl-input` defaulting to the uploaded filename stem, with a small tooltip explaining "Komt in de PDF-eigenschappen terecht; zichtbaar in DMS-systemen en schermlezers."
- [ ] **Toast or inline badge** on successful export: "Uw PDF is geëxporteerd als PDF/A-2b met Nederlandse taaltag en toegankelijke lak-markeringen." Small win; makes the feature visible.
- [ ] **Landing page bullet**: add a line to the trust / features section — *"Geëxporteerde PDF's voldoen aan PDF/A-2b en zijn voorgelezen-toegankelijk."* Coordinate with #44 and #40 content updates.

### Tests

- [ ] Unit tests for each post-processing step (language tag present, XMP fields present, annotation has `/Contents` and `/Alt`).
- [ ] Integration test: export a fixture PDF through the full chain and assert the output passes veraPDF PDF/A-2b validation.
- [ ] Regression test: bookmark-bearing source PDF round-trips with bookmarks preserved.
- [ ] No-log assertion: test that the user-supplied title string never appears in captured log output.
- [ ] Graceful-degradation test: Ghostscript unavailable → export still succeeds, warning logged.

## Acceptance Criteria

- Exported PDF has `/Lang (nl-NL)` on its catalog (verified by pikepdf in tests)
- Exported PDF has XMP metadata with title, description, producer, create date
- Each redacted rectangle has a matching accessible annotation with `/Contents` and `/Alt` containing the Dutch article description
- A screen reader (tested with at least one of: NVDA, VoiceOver) announces redaction article text when landing on a redacted passage
- Exported PDF validates as PDF/A-2b in veraPDF CI check
- Source PDF bookmarks are preserved in the export
- No user-supplied title string, no document content, and no redaction rationales appear in any log line
- Self-hosters without Ghostscript still get a working export (with a warning log) — the fallback path does not crash
- Landing page and export-success screen communicate the accessibility guarantees

## Not in Scope

- **PDF/UA-1 full conformance** — documented deferral, requires tagged source PDFs (enabled by #46) and structure-tree preservation through redaction. Becomes a follow-up todo once #46 ships.
- Tagged reading order for scanned documents — OCR + logical structure inference is a separate problem space
- HTML-format accessible export — possibly useful for some Woo publication workflows, but out of scope until a pilot asks
- Commercial PDF SDK integration (pdfix, iText) — conflicts with the open-source / self-host story (#43)
- Per-redaction user-editable rationale that gets surfaced as alt text — nice to have, gated on whether #19's redaction log already stores it per-mark
- Multi-language documents (Dutch + English mixed) — the `/Lang` tag is document-level only in v1; span-level language tagging requires the structure tree work deferred to PDF/UA-1

## Open Questions

- Should the XMP `dc:creator` field be populated? In v1 the app has no user identity (anonymous `/try`), so leave it blank. Once auth lands (Phase E), revisit.
- Should we default the title to the filename stem or leave it blank? Defaulting makes the field feel filled-in but may leak filename info into the PDF metadata in ways reviewers don't expect. Safer default: blank, with a placeholder `"Bijv. 'Besluit Woo-verzoek 2026-0123'"`.
- Does PyMuPDF's `apply_redactions` drop the catalog `/Lang` entry? Needs testing. If yes, we must re-add it in the post-process step, which is already how this todo is designed.
