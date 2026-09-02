# 00 — Client-First Architecture (PDFs Never Stored on Server)

- **Priority:** P0
- **Size:** XL (1–2 weeks)
- **Source:** Architectural decision based on privacy analysis
- **Depends on:** Nothing — this is the foundation
- **Blocks:** Everything else — all todos must respect this architecture

## Why

WOO Buddy processes privacy-sensitive government documents. In the current architecture, unredacted PDFs are stored permanently in MinIO, and sensitive entity text (BSNs, names, addresses) is stored permanently in PostgreSQL. This means the server administrator — and anyone who gains access to the server �� can read every original document and every detected entity.

For a SaaS product asking government employees to trust it with their most sensitive documents, this is a fundamental problem. The solution: **the PDF never leaves the user's browser**. The server processes text ephemerally and stores only non-sensitive metadata.

### The trust story (for the landing page)

"Je PDF verlaat nooit je browser. WOO Buddy analyseert de tekst, geeft suggesties, en vergeet alles weer. Alleen jouw lakbeslissingen worden opgeslagen — niet de documenten zelf."

## Architecture Overview

```
Browser (client)                          Server (backend)
────────────────                          ────────────────
PDF in memory                             
(File API + IndexedDB)                    
     │                                    
     ├── pdf.js extracts text             
     │   with positions (client-side)     
     │                                    
     ├── Sends extracted text ──────────► NER engine (Deduce) processes text
     │   via API                          LLM engine classifies entities
     │                                    Returns detections with positions
     │                                    *** Text discarded, NOT stored ***
     │                                    
     │   ◄────────── Detections ─────────┤
     │   (positions, types, tiers,        Stores ONLY metadata:
     │    articles — NO entity_text)      - detection position (bbox)
     │                                    - entity_type, tier, woo_article
     ├── Reviewer works through           - review_status, reviewer_id
     │   detections in browser            - motivation text (generic, not entity-specific)
     │   (all UI state client-side)       - audit log (actions, not content)
     │                                    
     └── Export: streams PDF ───────────► PyMuPDF applies redactions IN MEMORY
         to server (one-time,             Returns redacted PDF stream
         not stored)                      *** Original never written to disk ***
                                          *** No MinIO storage of originals ***
```

## Key Principles

1. **PDFs exist only in the browser.** Stored via the File API or IndexedDB for session persistence. Never uploaded to MinIO or any server storage.

2. **Text is processed ephemerally.** The server receives extracted text for NER/LLM analysis, returns results, and discards the text. No text content is written to the database, no request bodies are logged.

3. **The database stores decisions, not content.** Detection records contain: bounding box coordinates, entity type, tier, Woo article, review status, reviewer ID. They do NOT contain `entity_text` — the actual sensitive text.

4. **Export is a streaming operation.** The PDF is sent to the server once for final redaction, processed in-memory by PyMuPDF, and the redacted result is streamed back. The original is never written to disk.

5. **Server logs must not capture content.** Configure structlog to exclude request/response bodies. Error handlers must not dump text payloads into stack traces.

## Scope

### Client-side text extraction

- [ ] Build a text extraction service using pdf.js `page.getTextContent()`
- [ ] Extract text items with positions (transform matrix → bounding boxes)
- [ ] Produce structured output: `{ pages: [{ pageNum, textItems: [{ text, bbox, spans }] }] }`
- [ ] Handle edge cases: rotated text, multi-column layouts, embedded fonts
- [ ] Performance: extract text for a 100-page PDF within a few seconds in the browser
- [ ] Compare extraction quality with PyMuPDF output on sample documents — verify NER still works well on pdf.js-extracted text

### Client-side PDF persistence

- [ ] Store the loaded PDF in IndexedDB for persistence across page reloads within a session
- [ ] Handle storage limits: IndexedDB quota varies by browser (typically 50-80% of disk, but per-origin limits exist)
- [ ] Clear stored PDFs when the user explicitly closes/finishes a dossier
- [ ] Graceful degradation: if IndexedDB is full or unavailable, warn user that closing the tab loses their document
- [ ] For multi-document dossiers: manage multiple PDFs in IndexedDB concurrently

### Refactored backend: ephemeral text processing

- [ ] New endpoint: `POST /api/analyze` — accepts `{ pages: [{ pageNum, text, textItems }] }`, runs NER + LLM, returns detections
- [ ] NER engine accepts raw text instead of reading from MinIO/PyMuPDF
- [ ] LLM engine unchanged (already accepts text context)
- [ ] Text is processed in-memory and never written to database or logs
- [ ] Endpoint returns detection metadata WITHOUT `entity_text`

### Refactored database schema

- [ ] Remove `entity_text` column from `detections` table (or make it nullable and never populate in SaaS mode)
- [ ] Remove `original_bbox` if it stored text references — keep only coordinate data
- [ ] Audit log `details` JSONB must NOT contain entity text snippets — store action type + detection ID only
- [ ] Motivation texts: store generic article-based templates, not entity-specific text (the entity-specific version is composed client-side for display)
- [ ] Keep all non-content metadata: bbox coordinates, entity_type, tier, woo_article, review_status, reviewer_id, timestamps

### Ephemeral redaction export

- [ ] New endpoint: `POST /api/export/redact` — accepts PDF binary stream + detection metadata (bboxes, articles)
- [ ] PyMuPDF processes the PDF entirely in memory (no temp file on disk)
- [ ] Applies redaction annotations at the specified coordinates
- [ ] Streams the redacted PDF back to the client
- [ ] Optional: apply watermark for concept exports in the same pass
- [ ] The original PDF bytes are garbage-collected after the response completes — never written to MinIO

### Motivation report generation

- [ ] Two options (decide during implementation):
  - **Option A:** Generate client-side in the browser (has all the text + detection data)
  - **Option B:** Generate during the ephemeral export step (server has the PDF temporarily, can extract what it needs for the report, returns report alongside redacted PDF)
- [ ] Option B is simpler since the existing report generator works server-side, but adds content exposure during export
- [ ] Option A is more privacy-pure but requires a client-side PDF/document generator

### Remove MinIO dependency (for document storage)

- [ ] MinIO is no longer needed for storing original or redacted PDFs
- [ ] MinIO MAY still be used for:
  - Temporary export artifacts (dossier ZIPs) with a short TTL and auto-cleanup
  - Storing non-sensitive assets (public official CSV lists, org logos)
- [ ] Or remove MinIO entirely and handle exports as direct downloads
- [ ] Update `docker-compose.yml` accordingly

### Security: prevent accidental content leakage

- [ ] Configure structlog to never log request bodies on the `/api/analyze` and `/api/export/redact` endpoints
- [ ] Error handlers: catch exceptions from NER/LLM processing and return generic errors without echoing input text
- [ ] No text content in Sentry/GlitchTip error reports
- [ ] Rate-limit the analyze endpoint (prevent abuse of the NER/LLM pipeline)
- [ ] TLS required — text in transit must be encrypted

## Client-Side State Management

The browser now holds more state than before. Detection metadata comes from the server, but the PDF and its text are client-only.

```
IndexedDB (persistent within session)
├── PDF binary (per document)
├── Extracted text with positions (per document, per page)
└── Local detection display cache (entity_text for UI display, derived from text + bbox)

Server (PostgreSQL)
├── Dossier metadata (name, status, org_id)
├── Document metadata (filename, page_count, status — NO content)
├── Detection metadata (bbox, type, tier, article, status, reviewer — NO entity_text)
├── Page review status
├── Audit log (actions only, no content)
└── User/org/billing data
```

The client reconstructs `entity_text` for display by looking up the detection's bbox coordinates in the locally-held extracted text. This is a client-side join between server metadata and local content.

## What This Means for Multi-User Workflows

A supervisor reviewing a colleague's work:
1. They need the PDF — the original reviewer shares it via the organization's internal file system, email, or the supervisor opens it from the same source
2. They open it in WOO Buddy in their browser
3. The server has the detection metadata (positions, articles, decisions) which loads into their review interface
4. Their browser maps the metadata onto the PDF they have locally
5. They can see what was redacted, agree/disagree, leave comments referencing detection IDs

This works, but it means **both users must have the PDF**. The application should support this by allowing any org member to load a PDF for a document record that exists in their organization. The server stores the document record (filename, page count, status) but not the PDF itself.

## Acceptance Criteria

- Uploading a PDF in the browser does NOT send the file to the server
- Text extraction happens client-side via pdf.js and produces results usable by Deduce
- The `/api/analyze` endpoint processes text and returns detections without storing anything
- The `detections` table contains no `entity_text` values
- Server logs contain no document text content
- Export streams a redacted PDF back without writing the original to disk
- The application works end-to-end: upload → detect → review → export, with zero server-side document storage
- A second user can load the same PDF in their browser and see the detection metadata from the server

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| pdf.js text extraction quality differs from PyMuPDF | Compare on sample docs early; fall back to temporary server extraction if needed |
| IndexedDB storage limits for large PDFs | Warn user; suggest processing documents individually rather than loading 50 at once |
| Browser crash loses unsaved work | Auto-save detection state to server frequently (metadata only); PDF can be reloaded |
| Multi-user needs PDF sharing outside the app | Document this clearly in the UX; consider optional encrypted upload for teams (future) |
| Motivation report needs entity text | Generate during ephemeral export step or client-side |

## Not in Scope

- End-to-end encryption (Option C from the analysis) — adds complexity beyond what's needed
- Client-side NER (running Deduce in WASM) — not feasible with current Deduce architecture
- Client-side LLM (running Ollama in browser) — not feasible for 26B parameter models
- Offline mode (fully disconnected usage) — requires too much client-side infrastructure
