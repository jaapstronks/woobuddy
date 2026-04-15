# 46 — Client-Side Conversion Pipeline (Images, .txt, .docx, .zip)

- **Priority:** P1
- **Size:** L (3–7 days)
- **Source:** Multi-format document support plan 2026-04
- **Depends on:** Nothing (uses existing `/try` and `/review/[docId]` flows)
- **Blocks:** #47 (email / .msg ingestion) shares infrastructure but is independent scope

## Why

Today WOO Buddy only accepts PDF (`FileUpload.svelte:26` hard-codes `.pdf`). Real Woo verzoeken rarely arrive as clean PDFs — they are mixes of `.docx` conceptstukken, scanned letters as images, and bundled `.zip` archives. Forcing reviewers to pre-convert everything themselves is friction exactly at the moment they are evaluating whether WOO Buddy is worth adopting.

**But the trust sentence is the product.** *"Uw documenten verlaten nooit uw browser"* is the single line that makes WOO Buddy a yes for Dutch government procurement. The moment we have to say "except when converting .docx…" we weaken the only claim that distinguishes us from every other redaction tool. An earlier draft of this todo proposed an ephemeral server-side LibreOffice route and was rejected for exactly that reason.

So the design rule for this todo is: **every byte of every supported format stays in the browser, from upload through conversion through review through export.** No new server route. No Docker image bloat. Self-hosters get the same client-side path. The trust sentence gets *stronger*, not weaker:

> **Uw documenten verlaten nooit uw browser** — zelfs niet bij het omzetten van Word-bestanden of gescande afbeeldingen naar PDF. Alles gebeurt in het geheugen van uw eigen apparaat.

The cost of this design is fidelity. Client-side `.docx` → PDF is not as visually accurate as LibreOffice. We accept that, mitigate it with an explicit visual-verification step, and drop the formats where the JS library ecosystem is too weak to be safe.

## Formats in scope for V1

| Format | Approach | Fidelity |
|---|---|---|
| `.png` / `.jpg` / `.jpeg` / `.tif` / `.tiff` / `.webp` | `pdf-lib` wraps each image as a PDF page | Perfect (image is image) |
| `.txt` | Plain text laid out with `pdf-lib` text APIs | Perfect |
| `.docx` | `mammoth.js` → structured HTML → `pdfmake` (or `pdf-lib` custom walker) → text-selectable PDF | Good for text-heavy documents; complex tables, text boxes, and embedded objects may render poorly |
| `.zip` / `.7z` | Unpacked via `jszip`; each supported inner file enqueued as its own conversion | N/A |

**Critical invariant:** every produced PDF must have a **selectable text layer**. pdf.js `getTextContent()` is how detection works downstream. Any canvas-based "render to image PDF" shortcut silently breaks the entire detection pipeline — forbidden.

## Formats explicitly out of scope for V1

These don't have a mature-enough browser-side JS ecosystem to be trusted for privacy-sensitive Woo documents, and the server-side path is rejected. Users are told honestly:

| Format | Reason dropped | User copy |
|---|---|---|
| `.odt` / `.rtf` | JS library ecosystem too weak | "Zet uw ODT/RTF-bestand eerst zelf om naar PDF met LibreOffice of Word." |
| `.xlsx` / `.ods` | Cell-to-page layout is custom work, ugly output | "Voor spreadsheets: exporteer eerst naar PDF vanuit Excel of Calc." |
| `.eml` / `.msg` | Deserves its own scope — see #47 | Handled in #47 |
| `.pst` / `.mbox` | Mailbox archives; out of scope entirely | "Splits eerst in losse berichten." |
| Scanned / image-only PDFs without a text layer | OCR is a separate concern — see #49 | Handled in #49 |

These limitations live in a single "Ondersteunde bestandstypen" help link next to the upload area, with the copy above and a friendly *"We werken eraan meer formaten direct in uw browser te ondersteunen zodra we het veilig en zonder kwaliteitsverlies kunnen."*

## Scope

### Frontend — the whole todo lives here

- [ ] **Widen `FileUpload.svelte`** (`frontend/src/lib/components/shared/FileUpload.svelte:26`):
  - Replace the hard-coded `.pdf` check with a format-aware validator that accepts the V1 list above
  - Include per-format maximum size guards (images cap lower than docs since they bloat the PDF)
  - Reject unsupported formats with a Dutch error message that points to the help link
- [ ] **New `$lib/services/document-conversion/` module** — the client-side conversion dispatcher. Each format handler exports `convert(file: File) => Promise<Uint8Array>` returning PDF bytes:
  - `image-to-pdf.ts` — `pdf-lib` image embedding; one image per page, fit-to-page sizing
  - `text-to-pdf.ts` — `pdf-lib` text layout with Dutch-friendly font (Noto Sans) and reasonable line wrapping
  - `docx-to-pdf.ts` — `mammoth.js` → HTML → `pdfmake` (or `pdf-lib` custom walker). Preserves selectable text, handles headings, paragraphs, lists, simple tables. Text boxes / headers / footers / embedded images render best-effort or get dropped.
  - `zip-unpack.ts` — `jszip` based, returns a list of `File` objects for the supported inner entries
- [ ] **Visual verification step (mandatory)** between conversion and review. After any non-PDF source is converted, the user lands on a dedicated confirmation screen:
  - Shows the converted PDF in a preview pane (reuse `PdfViewer.svelte`)
  - Dutch headline: **"Dit is wat WOO Buddy gaat redigeren — klopt dit met het origineel?"**
  - Subcopy: *"We hebben uw bestand in uw browser omgezet naar PDF. Controleer of alle tekst en opmaak die u wilt redigeren ook daadwerkelijk in deze versie staat — soms raken complexe elementen zoals tekstvakken of kopteksten weg in de conversie."*
  - Two buttons: **"Ja, ga door met redigeren"** and **"Nee, opnieuw uploaden"**
  - Skipped entirely for PDF uploads (no conversion happened, no verification needed)
  - This is the safety net that turns a fidelity limitation into a step the reviewer actively uses
- [ ] **"Converting..." state** between upload and the verification step, using existing loading-state patterns from #22. Dutch copy makes the in-browser nature explicit: *"Uw bestand wordt omgezet naar PDF in uw eigen browser. Er wordt niets verstuurd."*
- [ ] **ZIP handling UX**: when a `.zip` is dropped, unpack in the browser, show a list of detected entries with per-file status badges (supported / unsupported), and let the user pick which one(s) to process. Since the app is single-document, "picking" means choosing one at a time in V1; a multi-doc queue can wait until #33 (orgs & data scoping) reshapes the app.
- [ ] **Help link next to upload area**: `sl-tooltip` or a small link that opens a Dutch-language "Ondersteunde bestandstypen" section explaining what works, what doesn't, and the recommended way to convert unsupported formats (use Word / LibreOffice / the browser's print-to-PDF).
- [ ] **Trust copy update** on landing page (`Hero.svelte` / landing trust section) and on `/try` upload area. The updated sentence is above. Coordinate wording with #44 and #40.

### Backend

**Nothing.** This todo is deliberately backend-free. No new route, no new dependency, no Docker image change. If you find yourself adding a backend file while implementing this, stop and re-read the "Why" section.

### Dependencies (frontend)

- `mammoth` — MIT, pure JS, mature. Used by Office 365 docs preview historically. `.docx` → HTML.
- `pdf-lib` — MIT, pure JS. PDF creation, image embedding, text.
- `pdfmake` — MIT, pure JS. Higher-level document builder, good for the docx → PDF translation because it preserves text-selectable output via proper text APIs.
- `jszip` — MIT, pure JS. ZIP unpacking.
- No new dependencies with a native or WASM binary that would balloon bundle size significantly. `pdf-lib` + `mammoth` + `pdfmake` + `jszip` is around 400 KB gzipped combined — acceptable for the `/try` route, and dynamically importable so the landing page stays lean.

### Privacy / logging guarantees

- [ ] No conversion-related telemetry that includes file contents, filenames, or format-specific field values. If we emit structured events for funnel analysis (Plausible #41), the event payload is `{format, size_bucket, outcome}` only.
- [ ] No `console.log` of document bytes, HTML intermediates, or any string pulled from user content during conversion. Add ESLint rules or a small lint check if helpful.
- [ ] The confirmation screen's preview is rendered from the in-memory `Uint8Array` only; nothing ever touches `fetch()`.

### Tests

- [ ] Unit tests per converter with fixtures checked into `frontend/src/lib/services/document-conversion/__fixtures__/`:
  - `.docx` round-trip: known text appears in the output PDF's text layer
  - Image: output PDF has correct page count and `pdf-lib` reports the embedded image
  - `.txt`: Dutch diacritics preserved, line wrapping correct
  - `.zip`: unpacked list matches fixture, unsupported entries flagged
- [ ] Integration test: upload `.docx` on `/try` → land on the verification step → confirm → land in `/review/[docId]` with working detections on the converted text
- [ ] Network isolation test: spy on `fetch` / `XMLHttpRequest` during a full conversion run and assert zero calls to anything except same-origin assets
- [ ] Fidelity regression suite: a small set of `.docx` fixtures with known layouts, asserting that specific known text strings appear in the output. Catches the case where a `mammoth` or `pdfmake` upgrade silently starts dropping content.

## Acceptance Criteria

- User can drop a `.docx`, `.txt`, image file, or `.zip` onto `/try` and eventually land in `/review/[docId]` with a working review session
- Every conversion runs entirely in the browser — verified by a network-isolation test that asserts zero outbound requests during the conversion step
- After any non-PDF conversion, the user sees the visual-verification screen before entering the review flow
- PDF uploads skip the verification step and behave exactly as today
- Unsupported format uploads (e.g. `.xlsx`) produce a clear Dutch error with a link to the "Ondersteunde bestandstypen" help copy
- Landing page and `/try` copy explicitly state the in-browser nature of conversion
- Bundle size impact for the `/try` route is measured and documented in the PR
- No filenames, no document content, no intermediate HTML, and no error stack traces containing document fragments appear anywhere in telemetry, logs, or the browser console

## Not in Scope

- `.odt`, `.rtf`, `.xlsx`, `.ods` (dropped with an honest "convert first" message)
- `.eml`, `.msg` (belong to #47)
- `.pst`, `.mbox` mailbox archives
- OCR for scanned PDFs and image-only PDFs (belongs to #49)
- Server-side conversion of any kind (explicitly rejected — see "Why")
- Full visual parity with LibreOffice for `.docx` (accepted limitation, mitigated by the verification step)
- Round-trip back to the original format — export is always PDF, which matches how Dutch gemeenten publish Woo besluiten
- Multi-document queues for `.zip` archives with many supported entries (single-document shape constraint from `CLAUDE.md`)

## Upgrade path for later (document, don't build)

- **WebAssembly LibreOffice** (Allotropia's work, ~200 MB bundle today) is the obvious future upgrade for full-fidelity `.docx`, `.odt`, `.xlsx` support without giving up the client-side story. When the bundle size drops to something acceptable (say < 30 MB gzipped for the office-format subset) this becomes a drop-in replacement for the mammoth-based path. Track upstream; revisit yearly.
- **Browser File System Access API** could let us stream very large files from disk through the converter without loading the whole thing into memory. Not needed for V1 size caps but worth knowing about if we ever raise them.

## Open Questions

- Should the verification step be skippable for users who have already verified a given file in a prior session? No — IndexedDB-based "already verified" state would require tracking file hashes, which is complexity the single-document shape doesn't justify. The step is cheap and catches a real failure mode.
- Do we want a "compare with original" side-by-side view in the verification step? Nice-to-have; out of V1. A single preview + confirmation button is enough.
- Should the docx converter warn when it *knows* it dropped something (e.g. a text box it couldn't render)? Yes, if `mammoth` emits a messages array noting ignored elements, surface a subtle Dutch warning above the verification preview: *"Let op: sommige complexe opmaak is mogelijk niet meegekomen in de conversie."* Treat this as a V1 polish item.
