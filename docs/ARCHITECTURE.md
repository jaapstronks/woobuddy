# WOO Buddy — Architecture

## Overview

WOO Buddy is a monorepo with two applications — a SvelteKit frontend and a FastAPI backend — backed by PostgreSQL for metadata and MinIO for PDF storage. Local LLM inference runs via Ollama with Gemma 4 26B.

```
┌─────────────────────────────────────────────────────────┐
│                    SvelteKit Frontend                    │
│  Landing (/) + Quick Try (/try) + App (/app)            │
│  Shoelace · Lucide · Tailwind · pdf.js                  │
└──────────────────────┬──────────────────────────────────┘
                       │ REST API (JSON)
┌──────────────────────▼──────────────────────────────────┐
│                    FastAPI Backend                        │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  PDF Engine   │  │  NER Engine   │  │  LLM Engine   │  │
│  │  (PyMuPDF)    │  │  (Deduce +    │  │  (Ollama +    │  │
│  │              │  │   regex)      │  │   Gemma 4)    │  │
│  └──────────────┘  └──────────────┘  └───────────────┘  │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐                      │
│  │  PostgreSQL   │  │    MinIO      │                      │
│  │  (metadata)   │  │  (PDF files)  │                      │
│  └──────────────┘  └──────────────┘                      │
└─────────────────────────────────────────────────────────┘
```

---

## Frontend (`frontend/`)

| Technology | Version | Purpose |
|-----------|---------|---------|
| SvelteKit | latest (Svelte 5) | Application framework, SSR + SPA |
| Shoelace | `@shoelace-style/shoelace@2.x` | Web component UI library |
| Lucide | `lucide-svelte` | Icons |
| Tailwind CSS | v4 | Utility styling, theming via `@theme` directive |
| pdf.js | `pdfjs-dist` | PDF rendering in browser |
| TypeScript | strict mode | Type safety |

### Key conventions

- **Svelte 5 runes mode** is enforced project-wide. Use `$state`, `$derived`, `$effect` — not legacy stores.
- **Shoelace web components** must be imported dynamically or in `onMount()` (no SSR for `customElements`).
- Shoelace events in Svelte 5 use the `onsl-*` pattern: `<sl-button onsl-focus={(e) => handle(e)}>`.
- The review page uses `export const ssr = false;` due to heavy browser-only dependencies (pdf.js, Shoelace).
- Components are organized by feature: `landing/`, `shared/`, `review/`, `dossier/`, `export/`.
- API client lives in `$lib/api/client.ts` — all API calls go through it.

### Component structure

```
src/lib/components/
├── landing/          Hero, HowItWorks, WhatWeDetect, YouDecide, OpenSource, Footer
├── shared/           Logo, FileUpload, ProcessingStatus
├── review/           PdfViewer, Tier1Card, Tier2Card, Tier3Panel, DetectionList, ...
├── dossier/          DossierCard, OfficialsList, DossierStats
└── export/           MotivationReport
```

### Route structure

```
/                                    Landing page (public)
/try                                 Quick single-PDF upload — no account needed
/app                                 Dashboard / dossier list
/app/dossier                         Create new dossier
/app/dossier/[id]                    Dossier detail: documents, officials list
/app/dossier/[id]/review/[docId]     Main review interface (95% of user time)
/app/export/[dossierId]              Export: redacted PDFs + motivation report
```

---

## Backend (`backend/`)

| Technology | Version | Purpose |
|-----------|---------|---------|
| FastAPI | latest | REST API, async throughout |
| PyMuPDF (fitz) | `pymupdf` | PDF text extraction + redaction |
| Deduce | `>=3.0` | Dutch de-identification NER |
| httpx | latest | Async HTTP for Ollama API |
| Anthropic SDK | `anthropic` | Optional fallback LLM provider |
| SQLAlchemy | v2 + async | ORM with `asyncpg` driver |
| Pydantic | v2 | Request/response validation |

### Key conventions

- **Async everywhere**: all route handlers and services use `async def`.
- **Deduce** is initialized once at startup (in FastAPI lifespan), not per-request (~2s load time).
- The LLM layer is abstracted behind an `LLMProvider` interface in `app/llm/provider.py`. Providers (Ollama, Anthropic) are swappable via `LLM_PROVIDER` env var.
- PDF redaction with PyMuPDF is **irreversible** — always work on a copy. Originals stay in MinIO permanently.

### Service layer

```
app/services/
├── pdf_engine.py         Text extraction with bounding boxes + redaction application
├── ner_engine.py         Deduce NER + regex patterns (Tier 1 + Tier 2 detection)
├── llm_engine.py         LLM analysis (Tier 2 role classification + Tier 3 content)
├── propagation.py        Name propagation logic across dossier
├── motivation.py         Motivation text generation per detection
└── export_engine.py      ZIP packaging + motivation report generation
```

### LLM abstraction

```
app/llm/
├── provider.py           Abstract LLMProvider interface
├── ollama.py             Ollama + Gemma 4 implementation
├── anthropic.py          Anthropic fallback implementation
└── prompts.py            System prompts for Tier 2 + Tier 3 tasks
```

---

## Infrastructure (Docker Compose)

| Service | Image | Purpose |
|---------|-------|---------|
| `frontend` | Node 22 Alpine | SvelteKit dev/production server |
| `api` | Python 3.12 | FastAPI application |
| `postgres` | postgres:16-alpine | Metadata, annotations, audit log |
| `minio` | minio/minio | S3-compatible PDF storage |

Ollama runs **natively on the host** (not in Docker) for Apple Silicon GPU acceleration. Docker containers reach it via `host.docker.internal:11434`.

---

## Database Schema

Six tables:

| Table | Purpose |
|-------|---------|
| `dossiers` | Woo request dossiers (title, request number, status, organization) |
| `documents` | PDFs within a dossier (filename, MinIO keys, page count, document date) |
| `detections` | Detected entities with classification (text, type, position, tier, confidence, Woo article, review status) |
| `public_officials` | Reference list of names per organization that should NOT be redacted |
| `audit_log` | Full audit trail (action, actor, details as JSONB) |
| `motivation_texts` | Generated motivation texts per detection, editable by reviewer |

### Key relationships

- `documents` belong to a `dossier`
- `detections` belong to a `document` and reference a tier (1/2/3)
- `detections` can reference a `propagated_from` detection for name propagation
- `motivation_texts` link to individual `detections`
- `public_officials` link to a dossier or organization

### Document status flow

```
uploaded → processing → review → approved → exported
```

### Dossier status flow

```
open → in_review → completed
```

---

## Detection Pipeline

The pipeline runs in five sequential stages:

### 1. PDF Text Extraction (PyMuPDF)

Extract every text span with its bounding box coordinates using `page.get_text("dict")`. This gives character-level position data needed to map detected entities back to visual locations in the PDF. Also extract document metadata (date, author) for the five-year rule check.

### 2. Tier 1: Hard Identifiers (Regex + Validation)

Pattern-match BSN (with 11-proef), IBAN, phone numbers, email addresses, postcodes, license plates, credit card numbers (Luhn check). Auto-classified with the appropriate Woo article and standard motivation text. No LLM call needed.

### 3. Tier 2: Contextual Personal Data (Deduce + LLM)

Run Deduce for Dutch de-identification (names, addresses, institutions). For each detected name, check against the organization's public officials reference list. For unmatched names, optionally call the LLM for role classification based on surrounding context. Detect special personal data via medical NER and keyword matching.

### 4. Tier 3: Content-Level Analysis (LLM)

Send relevant passages (identified by document type heuristics and keyword signals) to the LLM for analysis. The LLM identifies potential policy opinions, business-sensitive information, oversight-related content, and internal deliberation. Output is an annotation with possible grounds and a qualitative analysis — NOT a redaction decision.

### 5. Map Detections to PDF Coordinates

Fuzzy-match detected entity text back to the bounding boxes from step 1. Each detection maps to one or more `(page, bbox)` pairs. Tier 1 detections get black overlays, Tier 2 get colored highlights, Tier 3 get annotation markers.

### 6. Apply Redactions (after human review)

Using PyMuPDF's `add_redact_annot()` and `apply_redactions()`. Each redaction area shows the applicable Woo article number. This is irreversible — always on a copy.

---

## LLM Strategy

### Primary: Gemma 4 26B-A4B via Ollama (local)

A Mixture-of-Experts model that activates only 3.8B of its 26B parameters per token. All data stays local.

- Apache 2.0 license
- ~20-30 tok/s on Apple Silicon with full GPU offload
- Native function calling for structured JSON output
- 256K context window
- ~18GB RAM at Q4 quantization (fits on 48GB MacBook Pro with ~24GB headroom)

### Fallback: Anthropic API

Set `LLM_PROVIDER=anthropic` for comparison testing or when Ollama is unavailable.

### LLM usage per tier

| Tier | LLM usage |
|------|-----------|
| Tier 1 | None — regex + validation only |
| Tier 2 | Selective — role classification (citizen vs. official) and traceability assessment |
| Tier 3 | Primary engine — content analysis for policy opinions, business sensitivity, oversight |

### Function calling

Ollama's `/api/chat` with the `tools` parameter. Separate tools defined for:
- **Task A (Tier 2)**: Role classification — determine if a person name is a citizen, non-public civil servant, or public official acting in capacity.
- **Task B (Tier 3)**: Content analysis — analyze passages for potential redaction grounds with fact-vs-opinion assessment.

---

## Memory Budget (48GB MacBook Pro)

| Component | RAM |
|-----------|-----|
| Gemma 4 26B-A4B (Q4) | ~18GB |
| Deduce + regex | ~200MB |
| FastAPI + PyMuPDF | ~500MB |
| PostgreSQL | ~200MB |
| SvelteKit dev server | ~200MB |
| macOS + overhead | ~5GB |
| **Total** | **~24GB** |
| **Headroom** | **~24GB** |

---

## API Endpoints

```
POST   /api/dossiers                        Create dossier
GET    /api/dossiers                        List dossiers
GET    /api/dossiers/:id                    Get dossier with documents + stats

POST   /api/dossiers/:id/documents          Upload PDF(s)
GET    /api/documents/:id                   Get document metadata
GET    /api/documents/:id/pdf               Stream original PDF
GET    /api/documents/:id/pdf/page/:page    Render single page as image

POST   /api/documents/:id/detect            Trigger detection pipeline
GET    /api/documents/:id/detections        List all detections (filterable by tier)

PATCH  /api/detections/:id                  Update single detection
POST   /api/documents/:id/detections/batch  Batch update detections
POST   /api/detections/:id/propagate        Propagate a name decision across dossier

POST   /api/dossiers/:id/officials          Upload public officials reference list (CSV)
GET    /api/dossiers/:id/officials          Get current reference list
DELETE /api/dossiers/:id/officials/:name    Remove from reference list

POST   /api/documents/:id/redact            Apply accepted redactions
GET    /api/documents/:id/redacted-pdf      Download redacted PDF

POST   /api/dossiers/:id/export             Export dossier: ZIP + motivation report
GET    /api/dossiers/:id/export/status       Export job status
GET    /api/dossiers/:id/export/download     Download exported ZIP
GET    /api/dossiers/:id/motivation-report   Download motivation report separately
```

---

## Environment Variables

```env
# LLM Provider
LLM_PROVIDER=ollama                    # "ollama" or "anthropic"

# Ollama (primary — local)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma4:26b
OLLAMA_KEEP_ALIVE=-1

# Anthropic (fallback)
# ANTHROPIC_API_KEY=sk-ant-...
# ANTHROPIC_MODEL=claude-haiku-4-5-20251001

# Database
DATABASE_URL=postgresql+asyncpg://woobuddy:woobuddy@postgres:5432/woobuddy

# MinIO
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=woobuddy
MINIO_SECRET_KEY=woobuddy-secret
MINIO_BUCKET=documents

# Frontend
PUBLIC_API_URL=http://localhost:8000
```
