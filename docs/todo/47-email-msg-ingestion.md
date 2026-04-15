# 47 — Client-Side Email / .msg Thread Ingestion

- **Priority:** P1
- **Size:** M (1–3 days)
- **Source:** Multi-format document support plan 2026-04
- **Depends on:** #46 (shares the client-side conversion infrastructure, visual-verification screen, and file upload UX)
- **Blocks:** Nothing

## Why

Email exchanges are the single largest bulk content type in many Woo verzoeken. A typical ministerie verzoek contains dozens or hundreds of `.eml` or `.msg` files representing back-and-forth correspondence about a policy decision. Today a Woo-coördinator has no good way to process these in WOO Buddy — they'd have to manually print each email to PDF, concatenate them, and upload the result. That's hours of preprocessing before the tool even becomes useful.

Getting email ingestion right is arguably the highest-value format extension after `.docx`, because the **unit of review** for an email bundle is usually "the whole thread as one continuous document" — not one review session per message. The reviewer wants to read the thread top-to-bottom, redact names consistently across messages, and export a single redacted PDF. WOO Buddy should match that workflow.

As with #46, everything here runs **in the browser**. The trust sentence stays intact. Email formats are a natural fit for client-side conversion because emails are structurally simple — headers + body + attachment list — which is exactly the sweet spot where JS libraries are mature enough to be trusted.

## Formats

- [ ] **`.eml`** — standard RFC 5322. Parsed with a browser-compatible JS email parser (`postal-mime` is MIT-licensed, pure JS, actively maintained, and handles MIME multipart + attachments cleanly).
- [ ] **`.msg`** — Outlook proprietary format. Parsed with `@kenjiuno/msgreader` (MIT, pure JS, no native deps). Internally normalized to an in-memory representation compatible with the `.eml` rendering path.

Both paths are fully client-side. No server involvement. No new backend route.

## Rendering approach

The email-to-PDF rendering is the meaty part. The goal is a clean, readable, scannable PDF that preserves the metadata a Woo reviewer needs, with a **selectable text layer** (required for downstream detection).

- [ ] **Header block** at the top of each message: Van, Aan, CC, BCC (when present in `.msg`), Datum, Onderwerp. Rendered as a small table using `pdf-lib` or `pdfmake` text APIs.
- [ ] **Body rendered as plain text by default** — safer, no HTML parsing, no tracking pixels, no external CSS risk. Line breaks preserved. Quoted replies (`>`) visually indented.
- [ ] **Opt-in HTML body rendering** via a toggle on the upload screen ("HTML-opmaak behouden"). When enabled, HTML bodies are sanitized (strip `<script>`, strip `<link>`, strip `<style>` with external URLs, rewrite `<img src="http…">` to placeholder text) and then rendered into the PDF. Default is off because:
  - Most Woo reviewers care about content, not email styling
  - Plain text rendering is simpler and safer
  - HTML sanitization in JS is never 100% airtight against novel tracking techniques
- [ ] **Network isolation is non-negotiable.** Even in HTML mode, no `<img>`, `<link>`, `<iframe>`, or any other tag is allowed to trigger a network fetch during rendering. The rendering happens in a context where external URLs are rewritten to placeholders *before* any HTML parser touches them. This prevents tracking pixels and web bugs from revealing the reviewer's IP / timing / existence to an external party.
- [ ] **Attachment list** under the body: filename + size + type. Attachments themselves are not recursively inlined into the message body.

## Thread stitching (the reason this todo exists)

- [ ] When multiple `.eml` / `.msg` files are uploaded together, offer two modes on the upload screen:
  - **"Eén PDF van de hele thread"** (default): all messages sorted by `Date:` header ascending, stitched into a single PDF using `pdf-lib`'s page-copying API. Each message gets a page break and a small separator: *"Bericht N van M — [datum] — [onderwerp]"*. One review session, one export.
  - **"Eén review per e-mail"**: since the app is single-document shaped (see `CLAUDE.md`), this opens the first message immediately and leaves the remainder queued locally in IndexedDB for the user to step through. Cleaner multi-doc handling can wait until the app's single-document constraint is relaxed.
- [ ] Mode is chosen **before** conversion runs.
- [ ] Sorting is strict chronological by `Date:` header. Malformed or missing dates fall back to upload order with a small warning in the UI.

## Attachments

- [ ] Attachments detected during parsing are **listed in the rendered header block** (filename + size + type) but not inlined into the message body.
- [ ] On the upload screen, a secondary section shows "Bijlagen in deze e-mails" with a list. Each attachment of a supported type (any format #46 handles) has a checkbox: **"Ook redigeren"**. Checked attachments become additional review sessions via the #46 converter path.
- [ ] Unsupported attachment types are listed but greyed out with a "niet ondersteund" badge and a tooltip linking to the "Ondersteunde bestandstypen" help copy from #46.
- [ ] Full recursive inlining of attachments into the stitched PDF is out of scope. If a pilot asks for it, revisit.

## Trust copy

The upload screen for `.eml` / `.msg` reinforces the in-browser story:

> *"Uw e-mails en eventuele bijlagen worden in uw eigen browser omgezet naar PDF. Er wordt niets verstuurd — ook niet om HTML-afbeeldingen of tracking pixels op te halen. Die worden actief geblokkeerd."*

This is a genuinely novel guarantee compared to every other Woo tool, which typically uploads emails to a server and — in many cases — fetches external resources during rendering. Make it visible.

## Visual-verification step

- [ ] Reuse the verification screen from #46. After email conversion, show the produced PDF (or the stitched thread PDF) in a preview pane with the same Dutch headline: **"Dit is wat WOO Buddy gaat redigeren — klopt dit met het origineel?"**
- [ ] For email-specific nuance, add a line below: *"Controleer dat alle berichten in de juiste volgorde staan en dat bijlagen die u wilt redigeren apart zijn toegevoegd."*

## Scope

### Frontend

- [ ] New handlers in `$lib/services/document-conversion/` (the module created in #46):
  - `eml-to-pdf.ts` — `postal-mime` → normalized message object → render header + body → `pdf-lib` PDF
  - `msg-to-pdf.ts` — `msgreader` → normalized message object → same rendering path
  - `email-thread-stitch.ts` — sort by date, concatenate via `pdf-lib` page copy, insert separators
  - `html-email-sanitize.ts` — sanitize HTML with all external URLs rewritten to placeholders before any parser touches it (belt-and-braces: URL rewrite first, DOMPurify or similar second)
- [ ] Upload-screen extensions to `/try`:
  - Mode selector (thread vs. per-email) as a Shoelace `sl-radio-group`, only shown when multiple email files are selected
  - HTML rendering toggle as a Shoelace `sl-switch` with a Dutch tooltip explaining the safety trade-off and the network-block guarantee
  - Attachment list with per-item checkboxes
  - Progress counter during conversion: *"Bericht 12 van 87 wordt omgezet in uw browser…"*
- [ ] Widen `FileUpload.svelte` accept list to include `.eml` and `.msg` (on top of the formats added in #46)
- [ ] Reuse the "converting..." state and visual-verification step from #46

### Backend

**Nothing.** Same rule as #46. No server route, no new dependency.

### Dependencies (frontend)

- `postal-mime` — MIT, pure JS, modern email parser (supersedes older mailparser-style libs for browser use)
- `@kenjiuno/msgreader` — MIT, pure JS, Outlook `.msg` parsing
- `dompurify` — already a common choice for HTML sanitization; MIT; well-audited
- `pdf-lib` — already added in #46
- Combined bundle impact measured and documented in the PR

### Tests

- [ ] Plain-text `.eml` round-trip: known sender, subject, and body text appear in the output PDF's text layer
- [ ] HTML `.eml` with a tracking pixel: assert rendering completes with zero network requests (spy on `fetch` / `Image.src`)
- [ ] HTML `.eml` with an external stylesheet: assert no `<link>` ever hits the network
- [ ] Dutch diacritics in `.msg` subject and body: encoding preserved
- [ ] `.msg` with BCC: BCC field appears in the rendered header block
- [ ] Malformed `Date:` header: fallback sorting doesn't crash, warning surfaced
- [ ] Thread stitching of 3 messages: page order matches Date ascending, separators correctly formatted
- [ ] Attachment listing: filenames appear on the rendered page but not in any telemetry event
- [ ] Integration test: upload 5 `.eml` files → thread mode → verification step → review screen with all content indexed for detection

## Acceptance Criteria

- Uploading a single `.eml` with a plain-text body produces a clean in-browser PDF with a header block and readable, text-selectable content
- Uploading a single `.msg` works identically
- Uploading 10 `.eml` files together in thread mode produces one PDF with messages in chronological order
- HTML email toggle is off by default; turning it on still blocks all external network fetches (verified by test)
- Attachments are listed in the rendered header block and selected ones become review sessions
- The upload screen reinforces the "blocked tracking pixels" guarantee in Dutch copy
- No subject, body, or header value appears in any telemetry event or console log
- Every step runs in the browser — network isolation test asserts zero outbound requests during conversion

## Not in Scope

- `.pst` / `.mbox` full mailbox archive parsing
- Inline attachment rendering into the stitched thread PDF
- Full cross-upload email thread reconstruction (linking a reply from upload A to its parent in upload B)
- Automatic deduplication of duplicated messages across mailboxes
- Round-trip back to `.eml` / `.msg`
- Email address detection / redaction logic beyond what Tier 1 already does on extracted text
- Server-side anything (explicitly rejected — see #46)

## Open Questions

- Does `postal-mime` handle every `.eml` encoding quirk we'll see in real Dutch government mail (Windows-1252 bodies, quoted-printable edge cases)? Test with real fixtures before shipping. If gaps show up, `mailparser-mit` is a fallback, or we can post-process.
- Should signature-block detection carry over across stitched thread messages? Already covered by #20 (bulk sweep flows) — no extra work here.
- For very large threads (say 500+ messages), does `pdf-lib` handle the stitching in reasonable memory? Measure and document. If needed, process in chunks and stream to IndexedDB during construction.
