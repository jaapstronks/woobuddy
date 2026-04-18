# 60 — Client-side PDF redaction (eliminate export server-touch)

- **Priority:** P2
- **Size:** M–L (2–5 days; size depends on library choice and validation rigor)
- **Source:** Trust-claim correctness 2026-04 — the one remaining server-touch that contradicts the "uw PDF verlaat nooit uw browser" marketing claim
- **Depends on:** Nothing (can ship anytime)
- **Blocks:** The ability to use "uw PDF verlaat nooit uw browser" as a literal, defensible marketing claim

## Why

Today's export path (`backend/app/api/export.py`) is the **only** place in the system where document bytes leave the user's browser. The flow is:

1. Browser POSTs the full PDF to `/api/documents/{id}/export/redact-stream`
2. Server validates (magic bytes, 50 MB cap) and applies redactions in-memory with PyMuPDF
3. Server streams the redacted PDF back
4. Nothing is written to disk, nothing is logged

This is ephemeral and well-audited — `feedback_no_server_document_touch.md` explicitly grandfathers it as the one allowed exception. But it means our headline trust sentence *"uw PDF verlaat nooit uw browser"* is **not literally true**: during export the PDF does traverse our server.

For the pre-launch Gratis-tier push, we currently soften the claim to *"blijft in uw browser tijdens review"* and explain the export exception in the memo/trust copy. That is honest but verbose, and loses some marketing punch. Closing this gap — making the entire flow client-side — is what turns the nuanced claim back into a single-sentence one:

> **"Uw PDF verlaat nooit uw browser, ook niet bij export."**

That sentence is a meaningful differentiator vs every server-side competitor. It's worth shipping before we hit a broader-market push (Phase D → E transition).

## The core technical problem

Redacting a PDF *securely* is not the same as drawing a black rectangle over text. A visual overlay leaves the underlying text stream intact and extractable with any PDF reader's copy-paste. PyMuPDF does real text-layer removal — it rewrites the content streams to physically delete the redacted glyphs and any associated annotations, then renders the black overlay on top. Any client-side replacement **must do the same** or we silently ship a PDF that still contains the "redacted" personal data.

This is the single biggest reason we went server-side in the first place: PyMuPDF is battle-tested for irreversible redaction, and the JavaScript ecosystem's coverage was weaker. In 2026 the situation has shifted:

- **pdf-lib** can remove objects from PDFs and rewrite content streams. Mature and pure-JS, but redaction is not a first-class feature — we'd build on top of lower-level APIs.
- **mupdf.js** (WASM port of MuPDF — same engine PyMuPDF wraps) offers the *exact same* redaction primitives we use server-side. Bundle is ~10 MB gzipped; acceptable for the export flow as a dynamic import.
- **pdfjs-dist** can render but doesn't meaningfully edit; not suitable alone.

**Recommended path:** mupdf.js via dynamic import on the export screen. It gives us identical semantics to PyMuPDF with no server-touch, and the 10 MB bundle only loads when the user hits export (not on every page view).

## Scope

### Library integration

- [ ] Add `mupdf` (via npm) as a frontend dependency, gated behind a dynamic `import()` in the export flow so it doesn't inflate the initial bundle
- [ ] New `$lib/services/pdf-redaction/` module with `applyRedactionsClientSide(pdfBytes, redactions): Promise<Uint8Array>` matching the shape of the current `_build_redactions` → PyMuPDF pipeline in `backend/app/api/export.py`
- [ ] Preserve all current export guarantees: text-layer removal (not overlay-only), metadata scrubbing, Woo-article annotation on each redaction region

### Validation (the non-negotiable bit)

- [ ] **Post-redaction extraction test**, run automatically as part of the export flow before handing the file to the user:
  - Re-open the produced PDF via pdf.js `getTextContent()`
  - For each redacted bbox, assert that the extractable text inside that region is empty or has been replaced with the annotation marker (never the original string)
  - If any assertion fails, **do not deliver the file**; show a clear error, fall back to the server path (or block with an explanation) while we investigate
- [ ] **Golden-file test suite** in `frontend/src/lib/services/pdf-redaction/__fixtures__/` with representative inputs (simple text PDF, OCR'd scan, PDF with annotations, PDF with form fields) and expected post-redaction text extractions. Runs in CI; regression protection against mupdf.js upgrades silently changing redaction semantics.
- [ ] **Side-by-side byte-level test** against the current PyMuPDF output: for the golden fixtures, both paths should produce PDFs that fail the same extraction test (i.e. both successfully remove the text layer in the redacted regions).

### UX

- [ ] "Exporteren" button triggers the client-side path by default; the export screen shows a brief "Redactie wordt toegepast in uw browser…" state (existing loading-state patterns from #22)
- [ ] If the client-side validation assertion fails, show an explicit Dutch error: *"De redactie kon niet veilig in uw browser worden afgerond. Probeer het opnieuw — als het blijft mislukken, verwijder het bestand niet en neem contact op."* (never auto-fallback silently to the server path; that would reintroduce the server-touch invisibly)
- [ ] Update trust copy (landing, `/try`, memo-to-prospects, `docs/trust/`) to the single-sentence form once #60 ships: *"Uw PDF verlaat nooit uw browser."* Coordinate with #40, #44, #46 copy owners.

### Server-side cleanup

- [ ] Keep `/api/documents/{id}/export/redact-stream` temporarily behind a feature flag as a fallback for self-hosters who haven't yet upgraded to a mupdf.js-capable browser (unlikely — WebAssembly is universal — but harmless to keep the route available during the transition)
- [ ] After one release cycle of successful client-side use, **remove the server route and PyMuPDF dependency entirely**. The codebase becomes materially simpler: one fewer Docker dependency, one fewer API surface to audit, one fewer log-secret rule to maintain.
- [ ] Update `docs/self-hosting/` to explain that export now runs in the browser and no server-side PDF engine is required

### Performance

- [ ] Measure: client-side redaction of a typical 50-page PDF on mid-tier hardware (M1 Air, 16 GB RAM) should complete in <5s. Document actual numbers in the PR.
- [ ] Large-document path (~500 pages, ~40 MB): acceptable if <30s with a visible progress indicator. Document the upper bound.
- [ ] Bundle: the mupdf.js import must be dynamic and gated to the export route — no cost on `/` or the initial review load.

### Tests

- [ ] Unit tests for the client-side redactor against the fixtures above
- [ ] Integration test: full review → client-side export → downloaded file passes the post-redaction extraction test
- [ ] Network-isolation test: during a client-side export, zero outbound requests except for static asset loads that were already cached. Specifically, no POST to `/api/documents/*/export/*`.
- [ ] Regression test: a fixture that previously exposed a PyMuPDF-specific bug also passes under mupdf.js (sanity that we haven't lost capability)

## Acceptance

- User can complete a full review → export flow without any PDF bytes leaving the browser
- Post-redaction extraction test passes for all golden fixtures and runs automatically in the export flow
- Trust copy updated across landing + `/try` + docs with the single-sentence literal claim
- Server-side export route either removed or explicitly feature-flagged off by default
- Self-host documentation updated: no PyMuPDF dependency required for the default path
- CI includes the golden-file regression suite

## Not in scope

- OCR-based redaction for scanned PDFs without a text layer — that's #49 (done) + a separate consideration; the redaction here assumes the text layer OCR added is what we redact
- Byte-level equivalence between PyMuPDF and mupdf.js output (the two engines may produce slightly different byte sequences; what matters is functional equivalence — the redacted regions contain no extractable text)
- Client-side signing / certification of the exported PDF (digital signatures, PDF/A conformance) — coordinate with #48 (accessible PDF export), which is the right place for those concerns
- Resurrecting the server-side path as a performance optimization for large documents — if mupdf.js can't handle a size, we cap the size rather than fall back invisibly to the server

## Open questions

- **Bundle size tolerance**: 10 MB gzipped is on the high side. Measure actual hit on the export route's time-to-interactive. If it's a problem, investigate whether a slimmer mupdf.js build profile exists that strips features we don't use (rendering, form fields).
- **Browser compatibility floor**: mupdf.js requires WebAssembly and SharedArrayBuffer (the latter needs COOP/COEP headers). Confirm our Caddy config already sets these, or add them as part of this todo. COOP/COEP can break third-party embeds — verify the impact on Plausible and any future SSO redirects.
- **Self-host without WASM**: can we point self-hosters at an older-browser fallback? Probably not worth it — every government browser in 2026 supports WASM. Document the requirement and move on.
- **Do we want to ship this BEFORE or AFTER public launch?** Argument for before: the trust claim becomes simple and undeniable, which is a stronger launch story. Argument for after: launch is already close, and nuanced-but-honest trust copy is acceptable. Recommendation: **ship after Phase D launch** as the first post-launch polish win, framed externally as *"we've now made our privacy promise literal."* That's its own small press moment.

## Strategic note

This is one of those todos where the code change is moderate but the *communication* impact is large. The work isn't just technical — once shipped, rewrite every public surface (landing, docs, LinkedIn intro copy, sales deck if we have one) to use the stronger claim. Coordinate with whoever owns the marketing copy at that time. The whole point is the sentence; ship it loudly.
