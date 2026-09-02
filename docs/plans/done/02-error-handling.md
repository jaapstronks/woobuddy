# 02 — Error Handling

- **Priority:** P0
- **Size:** M (1–3 days)
- **Source:** Testing & Polish briefing, Section 3 (rescoped for single-document + client-first flow)
- **Depends on:** #00 (Client-first architecture — error scenarios differ with client-side PDFs)
- **Blocks:** Nothing directly, but needed before real users

## Why

The briefings describe happy paths only. Real usage will hit: corrupt PDFs, scanned
PDFs with no selectable text, password-protected PDFs, network drops, oversized files,
full IndexedDB. Without graceful handling, these become confusing failures for the
reviewer.

## Scope notes (vs. original briefing)

Since this todo was first written:

- **Tier 3 LLM analysis is disabled** in the current pipeline (`services/llm_engine.py`).
  Ollama is not called during `/api/analyze`, so there is no user-visible banner needed
  for Ollama unavailability today. We still add a non-fatal startup probe and expose
  LLM status through `/api/health` so the banner can be wired up when Tier 3 is
  re-enabled.
- **Single-document flow** (`/try` → `/review/[docId]`). There is no offline queue of
  unsaved decisions, no multi-document list, and no cross-document state. Decisions
  are posted immediately via `updateDetection`; retry is per-call, not a background
  drain.
- **File size 50 MB** is already enforced client-side by `FileUpload.svelte` and again
  on the export endpoint (`MAX_PDF_SIZE`).

## Scope

### Backend: LLM reachability (advisory, Tier 3 dormant)

- [x] FastAPI startup does not crash if Ollama or Deduce are unavailable
      (`main.py` lifespan already logs a warning without re-raising).
- [ ] Extend `/api/health` to probe the configured LLM provider with a short timeout
      and return `{ status, ollama: "ok" | "unreachable" | "disabled" }`. Non-fatal
      so the endpoint still returns 200.
- [ ] Log a single startup warning if the LLM provider is unreachable.

### Frontend: PDF errors (client-side, since PDFs live in the browser)

- [ ] Corrupt / unreadable PDF → `pdfjsLib.getDocument()` throws → clear Dutch error in
      the `/try` page instead of the raw stack trace.
- [ ] Password-protected PDF → pdf.js raises a `PasswordException` → show a Dutch
      message ("Dit PDF-bestand is met een wachtwoord beveiligd. WOO Buddy kan
      beveiligde PDF's niet verwerken.").
- [ ] Scanned PDF (no extractable text) → after `extractText()` returns an empty
      full-text, block analysis and show: "Dit document bevat geen selecteerbare
      tekst (waarschijnlijk een gescande PDF). Automatische detectie werkt niet;
      handmatige lakking komt in een latere versie."
- [ ] 50 MB limit is already enforced in `FileUpload.svelte` — keep.
- [ ] Large PDFs (≥ 20 MB or ≥ 100 pages) → show an informational note during
      extraction so the user knows the wait is expected.
- [ ] IndexedDB: use `navigator.storage.estimate()` before `storePdf()` and refuse up
      front with: "Onvoldoende opslagruimte in de browser. Sluit andere tabbladen of
      verwijder het vorige document in WOO Buddy." Keep the existing
      `QuotaExceededError` handler as a fallback.

### Frontend: Network errors

- [ ] `lib/api/client.ts`: single retry with 2 s backoff for transient network
      failures (`TypeError` from `fetch`, or 502/503/504). 4xx is not retried.
- [ ] Typed error (`ApiError` with `status`, `code`, `message`) so UI can distinguish
      network vs. validation failures.
- [ ] `/try` page: if `analyzeDocument` fails after successful extraction + register,
      keep the extracted pages in memory and show a retry button that re-runs only
      the analyze step (no re-extraction, no re-upload of the PDF).
- [ ] `/review/[docId]`: export failures show an inline retry button (not a blank
      page). The PDF bytes are already in memory, so retry does not re-upload from
      IndexedDB.

### Not in Scope

- Mollie payment error handling (covered in the billing todo)
- Comprehensive retry/circuit-breaker patterns (future hardening)
- Offline queue for review decisions (out of scope until multi-document flow returns)
- Ollama unavailability banner in the UI (deferred until Tier 3 is re-enabled)
- OCR fallback for scanned PDFs (future — tracked with manual redaction work)

## Acceptance Criteria

- Opening a corrupt PDF on `/try` shows a Dutch error, not a stack trace.
- Opening a password-protected PDF on `/try` shows a specific Dutch message.
- Opening a scanned PDF on `/try` shows a "no selectable text" message instead of
  producing zero detections silently.
- Uploading a >50 MB file is rejected client-side with a clear size message (already
  the case — covered by regression check).
- Killing the backend between extraction and `/api/analyze` shows a retry button on
  the `/try` page and does not force a re-upload.
- Killing the backend while exporting from `/review/[docId]` shows an inline retry
  button with the PDF bytes still in memory.
- `GET /api/health` returns 200 with an `ollama` field reflecting the provider's
  reachability (or `"disabled"` when the LLM tier is turned off).
