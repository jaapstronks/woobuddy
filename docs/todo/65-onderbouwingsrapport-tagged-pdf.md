# 65 — Tagged PDF + bookmarks for the onderbouwingsrapport (PDF/UA-1)

- **Priority:** P2
- **Size:** S–M (half a day server-side, ~2 days client-side)
- **Phase:** C (polish & launch-ready)
- **Source:** Accessibility audit captured in `done/64-onderbouwingsrapport-export.md` (section "Accessibility").
- **Depends on:** #64 (shipped).
- **Blocks:** Nothing critical, but this is the last gap between the report being "passably accessible" and "PDF/UA-1 conformant".

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

## Implementation: server-side post-processing via PyMuPDF (reuse #48)

Route the generated report bytes through the same `backend/app/export/` pipeline that #48 already uses for the gelakte PDF. PyMuPDF + pikepdf can emit a tagged, PDF/A-2b-conformant document — exactly what #48 does for the redacted PDF.

**Why this is the obvious choice (no real trade-off):**

- **The report contains zero document content.** No `entity_text`, no extracted page text, no bbox snippets — by design (#64 explicitly omits all of it). It's metadata, SHA-256 hashes, counts, motivation strings keyed off Woo article codes, and static Woo article descriptions. The privacy-sensitive payload everyone cares about — the *redacted PDF* — already round-trips through this server pipeline for #48-style accessibility work, and the report is materially *less* sensitive than that.
- **The trust line on the landing page is about the source PDF.** "Uw originele PDF verlaat nooit uw browser" is what we promise on `/`, and it stays literally true: the report has no source-PDF content in it, and the source PDF itself doesn't go through this route.
- **The footer-copy change is small.** Today the report footer says "Gegenereerd met WOO Buddy — uw PDF heeft uw browser nooit verlaten". For a server-tagged report we trim the tail to "Gegenereerd met WOO Buddy" or restate it as "Het originele PDF-bestand heeft uw browser nooit verlaten." Either is honest; neither is a trust-story crisis.
- **Reachable accessibility quality is materially higher than the client-only alternative.** PyMuPDF + the existing post-processor produce output that passes PAC 2024 and Acrobat's PDF/UA checker; rolling our own structure tree against pdf-lib's low-level primitives would eat 1–2 days on Matterhorn-checker edge cases alone.

A purely client-side variant (build `/StructTreeRoot` and `/Outlines` against pdf-lib's low-level API in `frontend/src/lib/services/onderbouwing/report.ts`) is technically possible but is the worse use of the time: more work, lower-quality output, and the privacy reason that would justify it doesn't apply to a report with no document content.

## Scope

- [ ] New backend route, e.g. `POST /api/export/onderbouwing-tag`. Accepts the untagged PDF bytes (multipart, ≤ ~5 MB), returns a tagged PDF/A-2b. Streamed in/out, never written to disk, no logging of bodies (per `CLAUDE.md` rules) — same posture as `/api/export/redact`.
- [ ] Reuse the existing PyMuPDF + pikepdf helpers from `backend/app/export/` (#48). Apply the same lang tag, XMP, role-mapping, and PDF/A-2b conversion. Where #48 adds alt text on `/Subtype /Square` redaction annotations, the report has none — skip cleanly.
- [ ] Generate a real `/StructTreeRoot` with at least: `Document` → `Sect` (per section: cover, samenvatting, tabel, bijlage) → `H1` / `H2` for headings, `Table` / `TR` / `TH` / `TD` for the per-redactie table, `P` for body paragraphs.
- [ ] `/Outlines` with one entry per section, linking to the page where the section starts.
- [ ] Update the report footer to a phrasing that's honest about the round-trip — "Gegenereerd met WOO Buddy. Het originele PDF-bestand heeft uw browser nooit verlaten." or similar. The current "uw PDF heeft uw browser nooit verlaten" tail is the only line that needs softening, and only for the report.
- [ ] Frontend: after `buildOnderbouwingPdf` returns the untagged bytes, POST them to the new endpoint and use the tagged response in `bundleOnderbouwing`. If the endpoint is unreachable (self-host without backend, offline) fall back to the v1 untagged PDF and surface a small "rapport zonder structuur" hint so reviewers know.
- [ ] Keep the bundle filename: `onderbouwing_<file>_<date>.pdf` (or `.zip` when CSV is bundled).
- [ ] **No persistence whatsoever.** The route is privacy-equivalent to `/api/export/redact`: no `Document` row, no `Detection` rows, nothing to disk, no body logging. Rate-limit at the edge.

## Acceptance criteria

- [ ] Generated report passes PAC 2024 with zero errors and zero warnings.
- [ ] Acrobat Pro's "Make Accessible" wizard reports nothing missing.
- [ ] VoiceOver on macOS announces the document title (not the filename), the section headings, and the table cells with their column headers when reading the per-redactie table.
- [ ] Bookmarks pane in Acrobat shows four entries: Voorblad, Samenvatting, Tabel met redacties, Bijlage A — Toelichting per Woo-grond. Clicking each jumps to the right page.
- [ ] `/api/export/onderbouwing-tag` neither logs request bodies nor persists anything to PostgreSQL. Verified by inspecting `backend/app/main.py` middleware and the route handler.
- [ ] Report footer copy reflects the round-trip honestly.
- [ ] Self-hosters running frontend-only or with the backend offline get the untagged v1 report instead of a 500 — the fallback is covered by a frontend integration test.

## Open questions

- **Validator delta:** PAC 2024 and Acrobat sometimes disagree on edge cases. If they conflict, defer to Acrobat (it's what the recipient will actually use).

## Not in scope

- Tagging the gelakte PDF differently than #48 already does. This todo only touches the *onderbouwingsrapport*.
- Adding screen-reader-only "long descriptions" of the table beyond the visible motivation column. The motivation column already contains a full Dutch sentence per redaction; that's the long description.
- Sign-language video, audio descriptions, or other media accommodations. Not relevant for a textual report.
