# 65 — Tagged PDF + bookmarks for the onderbouwingsrapport (PDF/UA-1)

- **Priority:** P2
- **Size:** S–M (shipped client-side; see notes below for the path actually taken)
- **Phase:** C (polish & launch-ready)
- **Status:** **Shipped 2026-04-28** on `feat/onderbouwing-tagged-pdf`. Implemented client-side in pdf-lib (NOT via the PyMuPDF round-trip the original spec proposed — see "Implementation note" below). Adds `/StructTreeRoot` with `Document → Sect → H1/H2/H3/P/Table/TR/TH/TD` elements, a `/ParentTree` linking each MCID back to its owning structure element, per-page `/StructParents` indices, and a flat `/Outlines` with the four section bookmarks (Voorblad, Samenvatting, Tabel met redacties, Bijlage A). Decorative content (footer page numbers, divider lines, table row backgrounds, column separators) is wrapped in `/Artifact BMC ... EMC` so it stays out of the structure tree (PDF/UA Matterhorn 14-001).
- **Source:** Accessibility audit captured in `done/64-onderbouwingsrapport-export.md` (section "Accessibility").
- **Depends on:** #64 (shipped).
- **Blocks:** Nothing.

## Implementation note — why client-side, not server-side

The original spec proposed routing the report through the existing `backend/app/services/pdf_accessibility.py` pipeline (PyMuPDF + pikepdf, the same one #48 uses for the gelakte PDF) on the assumption it could synthesize a structure tree. **It cannot.** The pipeline's own docstring is explicit: "PDF/UA-1 (full structure-tree conformance) is intentionally out of scope — it requires a tagged source document, which PyMuPDF cannot synthesize from a flat PDF." The half-day estimate was based on that wrong premise.

Three viable paths emerged:

1. **Client-side via pdf-lib low-level primitives** — verbose but the only path with full layout context. ~2 days. **Picked.**
2. Server-side via pikepdf primitives — same shape of work as path 1, just in Python. ~2 days, no upside.
3. Rewrite the renderer in Python with reportlab/fpdf2 — native tagged-PDF support, but throws away ~800 lines of working pdf-lib code and changes the privacy posture. ~2 days, real loss.

Path 1 keeps the architecture intact: client renders, lazy-loads pdf-lib, no new server route. The trust line ("uw originele PDF verlaat nooit uw browser") survives unchanged. The cost is a more verbose `structure.ts` module against pdf-lib's primitive API.

## Why

The onderbouwingsrapport is, by design, a document that ends up in the hands of someone who didn't ask to receive it: a bezwaarmaker, a journalist, a civil-society researcher, or someone reviewing a large set of Woo-besluiten. Some of those readers use assistive technology. Dutch government recipients are also bound by the *Tijdelijk besluit digitale toegankelijkheid overheid* (2018), which references EN 301 549 → WCAG 2.1 AA → PDF/UA-1.

The v1 report (#64) ships with the cheap accessibility wins:

- `/Lang nl-NL`, `/Title`, `/ViewerPreferences /DisplayDocTitle true`, `/MarkInfo /Marked true`
- WCAG 1.4.3 AA contrast on every text colour
- Real selectable text, geometric reading order, no colour-only signalling
- Fuller metadata (Author / Subject / Keywords / dates)

The two gaps that remain are the ones pdf-lib doesn't expose with a high-level API:

1. **No `/StructTreeRoot`** — without a structure tree, headings aren't announced as headings, and table cells aren't associated with their column headers. AT users get the geometric fall-back, which works for a single-column report but isn't PDF/UA-1.
2. **No `/Outlines`** — readers can't jump between the four sections (voorblad → samenvatting → tabel → bijlage A) using the bookmarks panel or AT navigation.

This todo closes those two gaps.

## What shipped

A new module `frontend/src/lib/services/onderbouwing/structure.ts` exposes a small `StructureBuilder` API that wraps pdf-lib's `pushOperators` and `PDFContext` primitives:

- `beginElement(role)` / `endElement()` — open and close a structure element under the current parent. Roles are a narrow union of standard PDF structure types (`Document`, `Sect`, `H1`, `H2`, `H3`, `P`, `Span`, `Table`, `TR`, `TH`, `TD`, `Caption`) — no custom roles, so we don't need a `/RoleMap`.
- `tag(page, pageIndex, draw)` — wrap the operations performed by `draw` in a `BDC /role <</MCID n>> ... EMC` sequence. Allocates a fresh MCID per page and records `(pageIndex, mcid)` against the currently open element.
- `artifact(page, draw)` — wrap drawing in `/Artifact BMC ... EMC`. Used for the footer (page numbers + wordmark), divider lines, table row backgrounds, and column separators. PDF/UA Matterhorn 14-001 requires every content-stream operator to be either tagged or marked as artifact — no unmarked operations allowed.
- `finalize(doc)` — at end of rendering, mounts `/StructTreeRoot` on the catalog with a tree of `StructElem` dicts (parent ↔ child cross-refs via `PDFRef`), builds the `/ParentTree` (a `/Nums` array keyed by each page's `/StructParents` index, value = array of element refs indexed by MCID), and sets `/StructParents` on each page.

A companion `mountOutline(doc, entries)` helper builds `/Outlines` from a flat list of `(title, pageIndex)` tuples — used by `report.ts` to capture each section's start page and emit four bookmarks at finalize time.

**Implementation gotchas worth recording:**

1. **`PDFOperatorArg` doesn't include `PDFDict`.** `BDC /H1 <</MCID 0>>` needs an inline-dict properties operand, but pdf-lib's operator-arg type union only covers `string | PDFName | PDFArray | PDFNumber | PDFString | PDFHexString`. Worked around by passing the dict as a verbatim `string` arg (`'<</MCID 0>>'`) — pdf-lib's `copyStringIntoBuffer` emits string args byte-for-byte without quoting, so the output is valid PDF syntax. Confirmed by integration tests that decompress content streams via `fflate`.
2. **Marked-content sequences cannot span pages.** Each line of wrapped text gets its own MCID; the parent `P` (or `TD`) accumulates MCID leaves from however many pages it spans. The structure element's `/K` array uses the explicit `<</Type /MCR /Pg pageRef /MCID n>>` form everywhere, never the implicit "MCID is just an integer" shortcut — robust to multi-page elements.
3. **`useObjectStreams: false`** for `doc.save()`. pdf-lib's default packs indirect objects into compressed object streams, which (a) makes the structure tree harder to debug and (b) historically tripped up PAC 2024. The few-kilobyte size cost is worth keeping the catalog plain.
4. **Footers are intentionally `/Artifact`.** ISO 32000-1 §14.8.2.2 specifies running headers/footers and page numbers as the canonical artifact case. Tagging them would have a screen reader say "Page 1 of 7. Page 2 of 7. Page 3 of 7..." between sections — exactly the user-hostile behaviour artifact tagging exists to prevent.
5. **No `/THead`.** PDF standard structure has `/THead`/`/TBody`/`/TFoot` for grouping table sections, but the basic `Table → TR → TH/TD` shape is sufficient for AT to associate cells with column headers, and skipping the optional grouping keeps the tree simple. Worth adding only if a validator complains.

## Acceptance criteria

- [x] `/StructTreeRoot` mounted on the catalog with a Document → Sect tree covering Voorblad, Samenvatting, Per-redactie tabel, Bijlage A.
- [x] Per-redactie table emits `Table → TR → TH/TD` so the column headers (Pagina, Type, Trap, Woo-artikel, Bron, Motivering) are associated with each data cell.
- [x] Cover key-value list, summary count rows, and provenance hash list also use `Table/TR/TH/TD` — they're labeled-data tables semantically, even if visually they read like lists.
- [x] `/MarkInfo /Marked true` on the catalog.
- [x] `/Outlines` with four entries; clicking jumps to the section start page (`/Fit` destination).
- [x] Per-page `/StructParents` set; `/ParentTree` built with one `/Nums` entry per page.
- [x] Per-page `/Tabs /S` set so focus traversal follows the structure tree (PDF/UA-1 Matterhorn 09-004). Required by Acrobat's "Tab order" check even on form-free pages; added in a follow-up commit after the first manual run flagged it.
- [x] Footer (wordmark + page X / Y) and divider lines wrapped in `/Artifact BMC ... EMC`.
- [x] No `entity_text` or document content in the report — covered by a regression test in `report.test.ts`.
- [x] Multi-page table doesn't explode the structure tree (single `Table` element across all pages, regression-tested with 60 detections).
- [x] Type check, lint, full vitest suite green.
- [x] **Manual validation in Acrobat Pro 2026 — passed.** All auto-checks green (Tagged PDF, Title, Primary language, Bookmarks, Tagged content, Tagged annotations, Tab order, Headings, Tables, Lists, Forms, Alternate Text, Character encoding, Tagged multimedia, Scripts, Navigation links). The two "Needs manual check" items (Logical Reading Order, Color contrast) are *always* manual — both verified independently (reading order via `pdfinfo -struct-text` walk; contrast via design audit — body text ≥ 7.7 : 1).
- [ ] PAC 2024 (Matterhorn) validation still pending — Windows-only, not blocking.

## Future follow-ups (not in this PR)

- **Optional PDF/A-2b round-trip.** A separate, opt-in server route that runs the existing #48 Ghostscript step on the report would add archival conformance for DMS systems that require it. No accessibility uplift, but harmless to layer on later.
- **Tagged source PDFs flowing through #46.** When the LibreOffice-headless conversion lands, uploaded `.docx` documents will arrive already tagged, and the gelakte PDF will inherit those tags through PyMuPDF redaction — automatically lifting the redacted PDF closer to PDF/UA-1 without any changes to this code path.
- **Validator-driven polish.** If PAC 2024 or Acrobat surface specific Matterhorn failures during manual validation, fix them under #65 follow-up commits rather than blocking this initial cut.

## Not in scope

- Tagging the gelakte PDF differently than #48 already does. This todo only touches the *onderbouwingsrapport*.
- Adding screen-reader-only "long descriptions" of the table beyond the visible motivation column. The motivation column already contains a full Dutch sentence per redaction; that's the long description.
- Sign-language video, audio descriptions, or other media accommodations. Not relevant for a textual report.
