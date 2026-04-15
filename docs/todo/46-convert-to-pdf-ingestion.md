# 46 — Convert-to-PDF Ingestion Pipeline

- **Priority:** P1
- **Size:** L (3–7 days)
- **Source:** Multi-format document support plan 2026-04
- **Depends on:** Nothing (uses existing `/try` and `/review/[docId]` flows)
- **Blocks:** #47 (email / .msg ingestion)

## Why

Today WOO Buddy only accepts PDF (`FileUpload.svelte` hard-codes `.pdf` at line 26). Real Woo verzoeken rarely arrive as clean PDFs — they are mixes of `.docx` conceptstukken, `.eml` / `.msg` email threads, `.xlsx` registers, and scanned images. Forcing reviewers to pre-convert everything themselves is friction exactly at the moment they are evaluating whether WOO Buddy is worth adopting.

The PDF-based review + export pipeline is the asset worth preserving: pdf.js extraction, bbox-accurate manual redaction, PyMuPDF export. Every attempt at "redact inside the native format" fails Woo compliance — search-and-replacing `█` in a `.docx` leaves tracked changes, misses headers/footers/text boxes, and isn't visually verified. Dead end.

The right design is to **convert-to-PDF at the front door** and keep everything else unchanged. This adds one ephemeral server touch at upload time, mirroring the ephemeral server touch that already happens at export. Both operations stay "in-memory, no persistence, no logging of document content."

## Scope

### Trust story update (critical)

This widens the client-first narrative and must be narrated honestly on the landing page and `/try`:

> Andere formaten dan PDF worden bij het uploaden ééns door onze server geleid en daar direct naar PDF omgezet. Het origineel wordt nooit opgeslagen, nooit gelogd, en nooit buiten het request-proces gebruikt. Vanaf dat moment geldt weer: uw PDF verlaat uw browser niet, behalve voor de eindredactie.

Update copy on the landing page trust section, the `/try` upload area subcopy, and `docs/reference/ARCHITECTURE.md` to reflect the addition.

### Formats in scope for v1

| Format | Conversion approach |
|---|---|
| `.docx` / `.doc` | LibreOffice headless (`soffice --convert-to pdf`) |
| `.odt` / `.rtf` / `.txt` | LibreOffice headless |
| `.xlsx` / `.ods` | LibreOffice headless with landscape fit-to-page |
| `.png` / `.jpg` / `.jpeg` / `.tif` / `.tiff` | PyMuPDF `fitz.open()` + `insert_image()` (no LibreOffice needed) |
| `.zip` / `.7z` | Unpacked **client-side**, each supported inner file enqueued individually |

`.eml` / `.msg` are explicitly **out of scope for this todo** — they have enough nuance (header rendering, attachments, multi-file threading) to deserve their own todo (#47). The infrastructure built here is a prerequisite for that work.

`.pst` / `.mbox` mailbox archives are out of scope entirely until a pilot asks.

### Backend

- [ ] **New route `POST /api/convert`** in `backend/app/api/convert.py`
  - Accepts a single multipart upload; returns `application/pdf` bytes.
  - **No persistence.** Nothing written to the database, nothing to disk outside a per-request tempdir that is cleaned in a `finally` block.
  - **No logging of filename or body.** Add the route to the request-id middleware's content-sensitive list (`backend/app/middleware/request_id.py:34`, alongside `/api/documents`).
  - Strict size cap (match existing upload cap — default 50 MB) and MIME/extension allowlist.
  - Hard timeout per conversion (30s is generous; LibreOffice warm cold-starts in ~2s and a 20-page docx converts in 1–3s warm).
  - Returns `400` with a generic Dutch error for unsupported formats; `413` for too large; `415` for MIME mismatch; `500` (generic message) for conversion failures.
- [ ] **LibreOffice adapter** in `backend/app/services/converter.py`
  - Per-format dispatcher: images → PyMuPDF path, everything else → LibreOffice path.
  - LibreOffice invocation via `subprocess` with a dedicated `-env:UserInstallation` per-request profile directory (prevents cross-request profile contamination) and `--norestore --nologo --nofirststartwizard`.
  - Capture stderr for observability but never log it verbatim (may contain fragments of document text on crashes).
  - Returns `bytes` on success, raises a typed `ConversionError` on failure.
- [ ] **Docker image update**: swap backend base image to one with LibreOffice available, or add `libreoffice-core libreoffice-writer libreoffice-calc` via `apt-get` in the backend Dockerfile. Document the ~400 MB image size increase in `docs/todo/43-open-source-release.md` so self-hosters aren't surprised.
- [ ] **Tests**: fixtures for each supported format in `backend/tests/fixtures/convert/` plus unit tests that assert: (a) round-tripping a known `.docx` returns a PDF PyMuPDF can open, (b) text content is preserved, (c) rejecting `.exe` / `.html` / unknown types returns 415, (d) timeouts surface cleanly, (e) no filename appears in logs.

### Frontend

- [ ] **Widen `FileUpload.svelte` accept list** (`frontend/src/lib/components/shared/FileUpload.svelte:26`) to include the full MIME / extension set above. Replace the hard-coded `.pdf` check with a format-aware validator.
- [ ] **Client-side ZIP unpacking** via a small wrapper around `jszip`. When a `.zip` is dropped, list its supported entries and enqueue each as a separate conversion. Unsupported entries are shown with a "niet ondersteund" badge and skipped.
- [ ] **New "converting..." state** in `/try` between upload and review. Shoelace `sl-progress-bar` + Dutch copy: "Uw document wordt omgezet naar PDF — dit gebeurt eenmalig in ons geheugen en wordt direct daarna weggegooid." Follow the loading-state patterns from #22.
- [ ] **Error states**: per-file error messages in Dutch for unsupported format, too large, conversion failed. Never echo server error text — use generic copy.
- [ ] Happy path on `/try`: upload `.docx` → convert → receive PDF bytes → hand off to existing pdf.js extraction → continue into `/review/[docId]` with zero changes to downstream code.

### Observability

- [ ] Structured log events (per client-first logging rule — no content, only metadata):
  - `convert.requested` — `{format, size_bytes}`
  - `convert.completed` — `{format, size_bytes_in, size_bytes_out, duration_ms}`
  - `convert.failed` — `{format, size_bytes, reason_code}` where `reason_code` is one of a fixed enum (`unsupported`, `timeout`, `libreoffice_error`, `image_decode_error`)
- [ ] No filenames, no stderr text, no PII of any kind in log fields.

## Acceptance Criteria

- User can drop a `.docx`, `.odt`, `.rtf`, `.xlsx`, or image file on `/try` and land in `/review/[docId]` with a working review session
- A `.zip` is unpacked in the browser and each supported entry becomes its own review session
- `POST /api/convert` with an unsupported type returns 415 with a generic Dutch message
- Conversion timeouts return a clean error without leaking stderr
- No document bytes, filenames, or stderr appear in any log line
- Docker image built from `backend/Dockerfile` contains LibreOffice and the route works end-to-end in `docker compose up api`
- veraPDF (or at minimum PyMuPDF's own parser) can open every conversion output without error
- Round-trip test fixtures cover each supported format

## Not in Scope

- `.eml` / `.msg` / email threading — belongs to #47, which depends on this todo
- `.pst` / `.mbox` mailbox archives
- HTML fidelity preservation for rich email bodies (also #47)
- Round-tripping back to the original format — the export is always PDF, which matches how Dutch gemeenten publish Woo besluiten
- Client-side docx→PDF conversion — no library is good enough; the server path is the realistic one
- Detection improvements specific to spreadsheet layouts or scanned-image OCR — out of scope here, possibly a future todo
- Auth or rate-limiting beyond a simple IP bucket (anonymous `/api/convert` must stay anonymous to preserve the no-signup `/try` promise)

## Open Questions

- Should we warm-pool LibreOffice processes to shave cold-start latency? Default answer: no, start simple and measure. If p95 latency is too high in pilot, add a warm pool in a follow-up.
- How to sandbox LibreOffice network access? It should never fetch remote resources (tracking pixels in docx headers, external stylesheets). Plan: run the backend container with egress blocked by default in production, document it for self-hosters.
