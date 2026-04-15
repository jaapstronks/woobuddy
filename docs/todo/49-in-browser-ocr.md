# 49 — In-Browser OCR for Scanned / Image-Only PDFs

- **Priority:** P2
- **Size:** M (1–3 days)
- **Source:** Multi-format document support plan 2026-04
- **Depends on:** Nothing (independent of #46 and #47)
- **Blocks:** Nothing

## Why

A large fraction of real Woo documents arrive as **scanned PDFs with no text layer** — old letters, signed contracts, printed-and-rescanned correspondence. Today WOO Buddy's detection pipeline silently fails on these: pdf.js `getTextContent()` returns nothing, so no Tier 1 / Tier 2 entities are detected, and the reviewer sees an empty detection list. The user then has to redact every name by hand using area selection, which is slow and error-prone.

The fix is OCR. The hard constraint is the trust sentence: *"Uw documenten verlaten nooit uw browser."* Any cloud OCR (Google Vision, AWS Textract, Azure) is instantly disqualified — not because it doesn't work, but because sending scanned Woo documents to a third-party API is precisely the thing our entire architecture exists to avoid.

The good news: **in-browser OCR is a solved problem.** `tesseract.js` is a well-maintained, MIT-licensed WebAssembly build of Tesseract 5 with Dutch language support (`nld.traineddata`). It runs entirely in the browser using Web Workers, produces a text layer with per-word bounding boxes, and has been shipped in production by multiple privacy-first tools. The Dutch language pack is about 10 MB; it can be loaded on-demand only when the user actually has a scanned document.

This turns "WOO Buddy doesn't work on scans" into "WOO Buddy runs OCR on scans in your browser, with Dutch language support, and still sends nothing anywhere." That is a huge win for the trust narrative.

## Scope

### Detection

- [ ] When a PDF is uploaded (directly or as the output of #46 / #47's conversion), check whether `pdf.js` `getTextContent()` returns meaningful text for any page. Meaningful means: more than a trivial character count *or* non-trivial extracted text spans. Define a threshold (e.g. < 50 characters across the whole document = "looks like a scan").
- [ ] If the document has a text layer: proceed as today, skip OCR entirely.
- [ ] If the document has no text layer: prompt the user before running OCR.

### OCR opt-in UX

- [ ] After detecting a text-less PDF, show a screen:
  - Dutch headline: **"Dit lijkt een gescand document te zijn"**
  - Body: *"WOO Buddy kan de tekst in uw browser herkennen (OCR) zodat de detectieregels kunnen werken. Hiervoor laden we éénmalig een Nederlands taalmodel van ongeveer 10 MB. Alles gebeurt in uw eigen browser — er wordt niets verstuurd."*
  - Two buttons: **"Ja, tekst herkennen"** and **"Nee, alleen handmatig redigeren"**
  - If the user declines, they land in the review flow with area-selection as the only redaction tool (existing #07 behavior)
- [ ] OCR runs with a progress indicator: page N of M, current language, estimated remaining time. OCR of a typical 20-page scan runs in 30–90 seconds in the browser — not instant, so the progress UX matters.

### OCR execution

- [ ] `tesseract.js` loaded **dynamically** — only when the OCR path is triggered, never on the landing page or in the default `/try` bundle
- [ ] Language: Dutch (`nld.traineddata`). Bundle the traineddata file as a static asset served from our own domain so there's no third-party CDN dependency (`cdn.jsdelivr.net` is the default tesseract.js CDN — explicitly override it to point at our own `/static/tesseract/` path).
- [ ] Run in a Web Worker to keep the main thread responsive
- [ ] Per-page processing with progress callbacks feeding the progress UI
- [ ] Output: per-word bounding boxes + recognized text

### Text layer injection

- [ ] After OCR completes, construct a new PDF with an **invisible text layer** overlaid on top of the original scanned image pages, using `pdf-lib`. Invisible-text techniques are standard (set the text rendering mode to "invisible" via PDF operators). The resulting PDF:
  - Looks visually identical to the original scan
  - Returns meaningful text via pdf.js `getTextContent()`
  - Has per-word bboxes positioned over the correct visual coordinates
- [ ] Alternative if the invisible-text approach proves fiddly with `pdf-lib`: keep the original PDF as-is and store the OCR result as a **parallel text-and-bbox map in IndexedDB**, then teach `bbox-text-resolver.ts` to consult it. Both approaches preserve the trust story; the invisible-text PDF is cleaner because downstream code doesn't need any changes.

### Downstream integration

- [ ] Once the text layer exists (either inside the PDF or in a parallel map), the normal detection pipeline runs unchanged. Tier 1 regex, Deduce NER, name wordlists — all of it works because they consume text strings and coordinates, not knowledge of how the text layer got there.
- [ ] Verify that the export pipeline still works correctly on an OCR'd document. PyMuPDF redactions apply to the visual layer; the invisible text layer should be redacted by the same annotation (or, if using the parallel-map approach, explicitly verify nothing weird happens).

### Privacy guarantees

- [ ] `tesseract.js` and `nld.traineddata` are self-hosted assets. No third-party CDN, no remote model download at runtime.
- [ ] Web Worker runs with no network access (verified by a test that spies on `fetch` from the worker context).
- [ ] No OCR result text, no recognized words, no bounding box data appears in any telemetry event or console log.
- [ ] Progress events contain only `{page, total_pages, pct}` — never content.

### Trust copy

Reinforce on the OCR opt-in screen and in the landing page's supported-formats help:

> *"Gescande documenten worden in uw browser gelezen met een lokaal Nederlands taalmodel. Er wordt niets verstuurd naar ons of naar derde partijen."*

This is another place where the client-first architecture turns a feature limitation into a marketing bullet.

### Tests

- [ ] Unit test: a known fixture PDF (scan of a printed Dutch letter with a name) produces a recognized text string containing the name
- [ ] Network isolation test: during OCR, zero outbound requests (including to the `tesseract.js` CDN — verify the override works)
- [ ] Integration test: scanned PDF → OCR → text layer → Tier 1 detection fires on an IBAN in the recognized text
- [ ] Decline path test: declining OCR lands the user in the review flow with an empty detection list and working area selection

## Acceptance Criteria

- A scanned PDF without a text layer triggers the OCR opt-in screen
- Accepting OCR produces a document where detection works exactly as it does for native PDFs
- OCR runs entirely in the browser with zero outbound network requests, verified by test
- The Dutch language pack is served from our own domain, not a third-party CDN
- Declining OCR produces a working review session with area-selection as the manual redaction tool
- Progress UI accurately reflects per-page OCR progress
- No OCR content appears in any telemetry or log
- Export on an OCR'd document produces a correctly redacted PDF

## Not in Scope

- Non-Dutch OCR languages (add `eng.traineddata` later if real users request it; keep the V1 bundle small)
- OCR on images embedded *inside* text PDFs (e.g. a signature scan pasted into a Word doc that was converted to PDF). Possible, but adds complexity for a small win — defer.
- Automatic OCR without user opt-in (performance cost is non-trivial; the opt-in is the right default)
- Handwriting recognition (Tesseract doesn't do this well; a different model class entirely)
- OCR quality tuning via preprocessing (deskew, binarize, denoise). `tesseract.js` defaults are good enough for most clean government scans; revisit if accuracy turns out to be a problem in pilot.
- Cloud OCR of any kind (explicitly rejected — violates the trust sentence)

## Open Questions

- Is the 10 MB Dutch language pack an acceptable one-time download cost on slow connections? For a government user on a wired office connection, yes. For a home reviewer on tethered mobile, it's noticeable. Cache aggressively via a long `Cache-Control` header and an install-time service worker warmup if it turns out to matter.
- Do we want to offer OCR-as-a-rerun on documents that *do* have a text layer but have garbled extraction? Possibly useful for badly-produced PDFs where pdf.js returns jumbled text. Defer until a pilot reports the problem.
- Does the invisible-text-layer PDF interact cleanly with the accessibility work in #48 (PDF/A-2b, `/Lang`, alt text on redactions)? Should work fine because the invisible layer just uses standard PDF text operators, but add an integration test once both todos ship.
