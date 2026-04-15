# 47 — Email / .msg Thread Ingestion

- **Priority:** P1
- **Size:** M (1–3 days)
- **Source:** Multi-format document support plan 2026-04
- **Depends on:** #46 (convert-to-PDF ingestion pipeline)
- **Blocks:** Nothing

## Why

Email exchanges are the single largest bulk content type in many Woo verzoeken. A typical ministerie verzoek contains hundreds of `.eml` or `.msg` files representing back-and-forth correspondence about a policy decision. Today a Woo-coördinator has no good way to process these in WOO Buddy — they'd have to manually print each email to PDF, concatenate them, and upload the result. That's hours of preprocessing before the tool even becomes useful.

Getting email ingestion right is arguably the highest-value format extension after `.docx`, because the **unit of review** for an email bundle is usually "the whole thread as one continuous document" — not one review session per message. The reviewer wants to read the thread top-to-bottom, redact names consistently across messages, and export a single redacted PDF. WOO Buddy should match that workflow.

This todo depends on #46 having built the `/api/convert` infrastructure, LibreOffice integration, and widened `FileUpload` accept list. Here we add the email-specific pieces on top.

## Scope

### Formats

- [ ] **`.eml`** — standard RFC 5322 email format. Parsed with Python stdlib `email` module.
- [ ] **`.msg`** — Outlook proprietary format. Parsed with the `extract-msg` library (MIT-licensed, pure-Python, no native deps). Convert to `.eml` internally, then use the same rendering path.

### Rendering approach

The email-to-PDF rendering is the meaty part. The goal is a clean, readable, scannable PDF that preserves the metadata a Woo reviewer needs:

- [ ] **Header block** at the top of each message: Van, Aan, CC, Datum, Onderwerp. Rendered as a small table.
- [ ] **Body** rendered as **plain text by default** — safer, no HTML parsing, no tracking pixels, no external CSS. Line breaks preserved. Quoted replies (`>`) visually indented.
- [ ] **Opt-in HTML body rendering** via a toggle on the upload screen ("HTML-opmaak behouden"). When enabled, HTML bodies are sanitized (remove `<img>` with remote URLs, remove `<script>`, remove `<link>`, strip external CSS) and then rendered. Default is off because most Woo reviewers care about content, not email styling, and the safer path is plain text.
- [ ] **Attachment list** under the body: filename + size + type. Attachments themselves are not recursively rendered inline in v1 — instead they are listed and can optionally be processed as separate review sessions (see "Attachments" below).
- [ ] Rendering is done via a small Jinja2 HTML template + WeasyPrint, OR via a plain-text `.docx` built on the fly and passed through LibreOffice from #46. **Recommend WeasyPrint** for simpler per-message rendering and better header control. WeasyPrint is a ~30 MB additional dependency.

### Thread stitching (the reason this todo exists)

- [ ] When multiple `.eml` / `.msg` files are uploaded together, offer two modes:
  - **"Eén PDF van de hele thread"** (default): all messages sorted by `Date:` header ascending, stitched into a single PDF via `pikepdf`. Each message gets a page break and a small separator with "Bericht N van M — [datum] — [onderwerp]". This becomes one review session, one export.
  - **"Eén review per e-mail"**: each message becomes its own review session. Useful when messages are unrelated (not a thread) or when reviewers explicitly want to treat them separately.
- [ ] Mode is chosen on the upload screen after files are selected but before conversion runs.
- [ ] Sorting is strict chronological by `Date:` header. Malformed dates fall back to upload order with a small warning in the UI.

### Attachments

- [ ] Attachments detected during `.eml` / `.msg` parsing are **listed in the rendered header block** (filename + size + type) but not inlined into the message body.
- [ ] The upload screen shows a secondary section: "Bijlagen in deze e-mails" with a list. Each attachment of a supported type (PDF, docx, images — whatever #46 supports) has a checkbox: "Ook redigeren". Checked attachments become additional review sessions.
- [ ] Unsupported attachment types are listed but greyed out with a "niet ondersteund" badge.
- [ ] This is kept simple on purpose — full recursive inlining of attachments into the stitched PDF is out of scope. If a pilot asks for it, revisit.

### Privacy guarantees (non-negotiable)

- [ ] HTML email rendering **must block all network requests** during WeasyPrint execution. WeasyPrint's `url_fetcher` is overridden with a function that refuses every external URL and logs nothing. This prevents tracking pixels, web bugs, and external CSS from phoning home with server IP + timing.
- [ ] `.msg` parsing with `extract-msg` must not write temp files outside the per-request tempdir.
- [ ] No header values, no subjects, no body fragments may appear in log lines. Log events are metadata-only: `{format, message_count, has_html, attachment_count, duration_ms}`.
- [ ] Same no-persistence rule as #46: ephemeral processing, per-request tempdir, `finally`-block cleanup.

### Frontend

- [ ] New upload sub-flow on `/try` triggered when any `.eml` / `.msg` file is present in the selection:
  - Mode selector (thread vs. per-email) as a Shoelace `sl-radio-group`
  - HTML rendering toggle as a Shoelace `sl-switch` (default off, with a tooltip explaining the privacy trade-off)
  - Attachment list with per-item checkboxes
  - Dutch copy explains the thread-stitching behaviour and the HTML toggle's privacy implications
- [ ] The "converting..." state from #46 is reused, but counts messages (e.g. "Bericht 12 van 87 wordt omgezet…")
- [ ] On completion: if thread mode, user lands in one `/review/[docId]` session with the stitched PDF. If per-email mode, user lands on a list picker first. (Or, simpler and more aligned with the single-document shape in `CLAUDE.md`: per-email mode opens the *first* message immediately and gives the user a way to navigate to the next one. Pick whichever is simpler — the single-doc shape of the app means per-email mode is inherently awkward, so thread mode should be the clear default.)

### Backend

- [ ] Extend `POST /api/convert` (from #46) to accept `.eml` / `.msg` with new query params / form fields: `mode=thread|per-email`, `render_html=true|false`.
- [ ] New helpers in `backend/app/services/converter.py`:
  - `convert_eml(bytes, render_html) -> bytes` — single message to PDF
  - `convert_msg(bytes, render_html) -> bytes` — via extract-msg → eml → convert_eml
  - `stitch_pdfs(list[bytes]) -> bytes` — pikepdf concat with page breaks
- [ ] Tests:
  - Plain-text email round-trip
  - HTML email with a tracking pixel: assert WeasyPrint's url_fetcher rejected the fetch
  - Malformed `Date:` header: assert fallback sorting doesn't crash
  - `.msg` with Dutch diacritics in subject and body: assert encoding is preserved
  - Thread stitching of 3 messages: assert page order matches Date ascending
  - Attachment listing: assert filenames appear on the rendered page but not in logs

## Acceptance Criteria

- Uploading a single `.eml` with a plain-text body produces a clean PDF with a header block and readable content
- Uploading a single `.msg` (Outlook format) works identically
- Uploading 10 `.eml` files together in thread mode produces one PDF with messages in chronological order, each on its own page
- Uploading the same 10 files in per-email mode produces 10 review sessions (or a list picker if that's the chosen UX)
- HTML email toggle is off by default; turning it on still blocks all external network fetches
- Attachments are listed in the rendered header block
- Selected supported attachments become their own review sessions
- No subject, body, or header value appears in any log line
- A round-trip test fixture set covers plain-text, HTML, `.msg`, multi-message threads, and Dutch diacritics

## Not in Scope

- `.pst` / `.mbox` full mailbox archive parsing
- Inline attachment rendering into the stitched thread PDF (attachments stay as separate review sessions)
- Full email thread reconstruction across separate uploads (e.g. linking a reply from upload A to its parent in upload B)
- Automatic deduplication of duplicated messages (common in email archives where the same thread appears in multiple mailboxes)
- Any kind of email address detection / redaction logic beyond what Tier 1 already does on the extracted text — detection runs on the converted PDF's text, same as any other document
- Round-trip back to `.eml` / `.msg` format — export is PDF

## Open Questions

- Should the header block include BCC when present in `.msg` files? Outlook `.msg` sometimes includes sender-side BCC. Dutch Woo practice is to redact BCC rather than omit it entirely, so **render it** and let the reviewer decide.
- Should we preserve email signature lines as-is or try to detect them for bulk redaction? Bulk signature handling is already covered by #20 (bulk sweep flows) — no extra work needed here.
