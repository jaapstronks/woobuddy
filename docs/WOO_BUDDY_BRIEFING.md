# WOO Buddy — Project Briefing

## Identity

- **Name**: WOO Buddy (always: WOO in caps, Buddy capitalized)
- **Domain**: woobuddy.nl
- **Tagline**: "Jouw slimme assistent voor het lakken van Woo-documenten"
- **License**: MIT
- **Personality**: Friendly, competent, approachable — like a knowledgeable colleague who makes a tedious legal process feel manageable. Not enterprise-cold, not cutesy.

---

## What It Does

WOO Buddy is an open-source, self-hostable web application that helps Dutch government employees process Woo (Wet open overheid) requests. It detects privacy-sensitive information in PDF documents and guides a human reviewer through the redaction process.

The core design principle is a **three-tier detection model** ("drietrapsraket") that recognizes that not all redaction decisions are equal. Hard identifiers like BSN numbers can be auto-redacted. Contextual personal data like names need a human confirmation. Content-level judgments like policy opinions require full human analysis with decision support. Each tier gets a different detection approach, confidence level, and UX pattern.

## Target Users

Government employees at Dutch municipalities, provinces, waterschappen, and rijksoverheid who handle Woo-verzoeken. Typically non-technical. They need a fast, clear interface that helps them make legally sound redaction decisions efficiently across potentially hundreds of documents per request.

---

## Legal Context: Woo Redaction Grounds

### Full overview of applicable articles

The Woo (chapter 5) defines the grounds for withholding information. The tool must cover all of these:

**Absolute grounds (Art. 5.1 lid 1) — always redact, no weighing needed:**

| Code | Ground | What to detect |
|------|--------|----------------|
| `5.1.1c` | Bedrijfs- en fabricagegegevens (vertrouwelijk verstrekt) | Business data that was provided confidentially to the government |
| `5.1.1d` | Bijzondere persoonsgegevens | Race/ethnicity, political opinions, religious beliefs, union membership, genetic/biometric data, health data, sexual orientation, criminal convictions |
| `5.1.1e` | Identificatienummers | BSN, BIG-nummer, AGB-code, patient numbers |

**Relative grounds (Art. 5.1 lid 2) — require weighing, human decides:**

| Code | Ground | What to detect |
|------|--------|----------------|
| `5.1.2a` | Internationale betrekkingen | Diplomatic relations, cross-border cooperation |
| `5.1.2c` | Opsporing/vervolging strafbare feiten | References to ongoing investigations |
| `5.1.2d` | Inspectie, controle en toezicht | Inspection strategies, enforcement plans, audit approaches |
| `5.1.2e` | Persoonlijke levenssfeer | Names of private persons, email addresses, phone numbers, home addresses, IBAN, dates of birth, license plates |
| `5.1.2f` | Bedrijfs- en fabricagegegevens (concurrentiegevoelig) | Competitive business information, trade secrets |
| `5.1.2h` | Beveiliging personen/bedrijven | Security details, access codes |
| `5.1.2i` | Goed functioneren bestuursorgaan | Information that would impair frank internal deliberation |

**Personal policy opinions (Art. 5.2) — special regime:**

| Code | Ground | What to detect |
|------|--------|----------------|
| `5.2` | Persoonlijke beleidsopvattingen | Internal policy advice, opinions, recommendations made during "intern beraad" |

Art. 5.2 is critical and complex: facts, prognoses, policy alternatives, and objectively-natured content are explicitly NOT personal policy opinions and may NOT be redacted. In formal administrative decision-making, personal policy opinions must be provided in anonymized form. The fact-vs-opinion distinction is the hardest judgment call in the entire Woo process.

**Residual ground:**

| Code | Ground | Note |
|------|--------|------|
| `5.1 lid 5` | Onevenredige benadeling | Only in exceptional cases; may not be used as subsidiary to other grounds |

### Cross-cutting legal rules

**Five-year rule (Art. 5.3):** Relative grounds do not automatically apply to information older than five years. The system must detect document dates and warn when a relative ground is applied to a document older than 5 years — extra justification is legally required.

**Environmental information (Art. 5.1 lid 6-7):** Environmental information (broad: air, water, soil, energy, emissions, health effects) has more limited redaction possibilities. The system must detect environmental content and flag which grounds are restricted.

**Third-party consultation (zienswijze):** When detected passages concern third parties (companies, citizens whose data appears), the system must flag that a formal consultation procedure may be required before publication.

### Exceptions — do NOT redact

- Names of public officials acting in official capacity (burgemeester, wethouders, gemeentesecretaris, mandated decision-makers)
- Information already publicly available (Handelsregister, public BIG-register)
- Information where the person has given explicit consent

### Redaction presentation requirements

- Each redacted area displays the applicable Woo article number (e.g., "5.1.2e")
- Redaction must be irreversible — underlying text truly removed, not just covered
- Non-redacted text remains machine-readable
- Documents must remain accessible (screen readers, sufficient contrast)
- Support configurable redaction color (black is standard; some organizations use different colors per ground)

---

## The Three-Tier Detection Model ("Drietrapsraket")

This is the core architectural concept. Each tier has a different detection approach, confidence level, and UX pattern.

### Tier 1: Hard Identifiers — Auto-redact with opt-out

**What:** Data detectable by pattern matching with very high certainty (>95%). BSN numbers (with 11-proef validation), IBAN numbers, phone numbers, email addresses, postcodes, license plates, credit card numbers (Luhn check), passport/driver's license numbers.

**Detection:** Regex + validation logic. No LLM needed.

**UX:** These are **redacted by default** when the document opens. The reviewer sees black bars already in place, each marked with a subtle icon indicating what type of identifier was found. One click to un-redact for exceptional cases (e.g., an IBAN that is a public payment account of a government body). No explanation panel needed — the justification is trivial and auto-generated.

**What the tool generates:** Article code (e.g., `5.1.1e`) and a standard motivation text that can go directly into the Woo decision.

### Tier 2: Context-Dependent Personal Data — Suggestion with one-click confirm

**What:** Data detectable via NER but where the redaction decision depends on context. Primarily art. 5.1.2e and partly 5.1.1d.

This tier is dominated by **names** — the most common category in redaction practice:
- Names of citizens → almost always redact
- Names of civil servants NOT acting in public capacity → redact
- Names of officials acting in public capacity (wethouders, directors, spokespersons) → often do NOT redact
- Names in mandate decisions → do NOT redact

Also: street addresses + house numbers, special personal data (medical information, diagnoses, medication names, ethnicity, religion, sexual orientation, criminal records), and function titles that are traceable to individuals at small organizations.

**Detection:** Deduce NER as primary, supplemented by role classification (citizen vs. official vs. administrator), a reference list of known public officials per organization, medical NER (UMLS terminology, medication names), and traceability assessment (does a job title + organization name uniquely identify a person?).

**UX:** Highlighted passages with a colored overlay (NOT black — that implies a final decision). Inline label showing the proposed ground (e.g., chip: "5.1.2e — persoonsnaam burger"). Confidence indicator (high/medium/low). One-click accept (✓) or reject (✗). Context panel (on hover or click) showing the reasoning: "Detected as personal name. Not found in the public officials list for [organization]. Proposed ground: art. 5.1.2e."

**Smart features:**
- **Name propagation:** When the reviewer confirms "J. de Vries" is a citizen at the first occurrence, all subsequent mentions of the same name are automatically accepted (with notification). This is critical for efficiency with large dossiers.
- **Role memory:** Classified names are remembered for the entire dossier, not just the current document.
- **Public officials reference list:** An importable list of names that should NOT be redacted (college B&W, council members, directors, spokespersons). Uploaded per organization/dossier.

**What the tool generates:** Article code plus a more specific motivation text, e.g.: "De naam van betrokkene is gelakt ter bescherming van de persoonlijke levenssfeer (art. 5.1 lid 2 sub e Woo). Het belang van eerbiediging van de persoonlijke levenssfeer weegt in dit geval zwaarder dan het belang van openbaarmaking."

### Tier 3: Content-Level Judgments — Annotation with decision support

**What:** Passages requiring substantive judgment that cannot be fully automated. The system's role shifts from *detection* to *signaling*. These are articles 5.2, 5.1.2d, 5.1.2f (competitive), 5.1.2i, 5.1.2a, and 5.1 lid 5.

Key categories:
- **Personal policy opinions (art. 5.2):** Internal advice, memos, draft texts. The hardest part: distinguishing facts from opinions. "Ik adviseer om..." is likely an opinion; "Het budget bedraagt €2M" is a fact.
- **Business data (art. 5.1.2f):** Financial data, revenue figures, client lists, strategy documents, tender offers.
- **Inspection and oversight (art. 5.1.2d):** Ongoing inspections, enforcement strategies, control plans.
- **Government functioning (art. 5.1.2i):** Interview records, integrity investigations, information that would impair frank deliberation.

**Detection:** LLM-based analysis looking for internal-deliberation indicators ("ik zou adviseren", "mijn inschatting is", "het lijkt mij verstandig"), business information indicators (financial data, client lists, strategy documents), oversight indicators (ongoing inspections, enforcement plans), and document type heuristics (a policy note has higher probability of containing opinions than a council decision).

**UX:** The system presents an **analysis**, NOT a redaction proposal. No confidence percentages — these are misleading at this tier. Instead, qualitative labels like "Mogelijk persoonlijke beleidsopvatting" or "Bevat mogelijk concurrentiegevoelige informatie."

The decision panel shows:
- Possible applicable grounds, ranked by likelihood
- A short analysis explaining why the passage was flagged
- A **fact-vs-opinion indicator** for art. 5.2 passages: "This sentence contains a factual statement about the budget" vs. "This sentence contains a value judgment about the plan's desirability" vs. "This passage contains both facts and opinions — consider redacting only the subjective parts"
- The relevant legal text (collapsible)
- For relative grounds: a checklist for the required interest-weighing
- Three decision buttons: **Redact** (reviewer selects the ground), **Don't redact** (reviewer notes why), **Defer** (marked for review by a colleague or jurist)

**What the tool generates:** The article code (chosen by the human, NOT the system), a draft motivation text that the reviewer can edit, and for relative grounds the outcome of the interest-weighing as structured text.

### Tier summary

| | Tier 1: Hard identifiers | Tier 2: Contextual personal data | Tier 3: Content judgments |
|---|---|---|---|
| **Detection** | Regex + validation | NER + role classification | LLM analysis |
| **Confidence** | >95% | 60-90% | 40-70% (not shown as %) |
| **Default state** | Auto-redacted | Suggested (highlighted) | Annotated (flagged) |
| **User action** | Opt-out (un-redact) | One-click confirm/reject | Full decision with support |
| **Motivation** | Auto-generated | Semi-auto with template | Human-written with draft |

---

## Architecture

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

## Tech Stack

### Frontend

| Technology | Version | Purpose |
|-----------|---------|---------|
| SvelteKit | latest (Svelte 5) | Application framework, SSR + SPA |
| Shoelace | `@shoelace-style/shoelace@2.x` | Web component UI library |
| Lucide | `lucide-svelte` | Icons |
| Tailwind CSS | v4 | Utility styling, theming |
| pdf.js | `pdfjs-dist` | PDF rendering in browser |
| TypeScript | strict mode | Type safety |

### Backend

| Technology | Version | Purpose |
|-----------|---------|---------|
| FastAPI | latest | REST API, async |
| PyMuPDF (fitz) | `pymupdf` | PDF text extraction + redaction |
| Deduce | `>=3.0` | Dutch de-identification |
| httpx | latest | Async HTTP for Ollama API |
| Anthropic SDK | `anthropic` | Optional fallback LLM provider |
| SQLAlchemy | v2 + async | ORM |
| Pydantic | v2 | Validation |
| Tesseract | `pytesseract` | OCR for scanned PDFs (phase 2) |

### Infrastructure (Docker Compose)

| Service | Image | Purpose |
|---------|-------|---------|
| `frontend` | Node 22 Alpine | SvelteKit |
| `api` | Python 3.12 | FastAPI |
| `postgres` | postgres:16-alpine | Metadata, annotations, audit log |
| `minio` | minio/minio | S3-compatible PDF storage |

---

## LLM Strategy

### Primary: Gemma 4 26B-A4B via Ollama (local)

A Mixture-of-Experts model that activates only 3.8B of its 26B parameters per token. Runs locally — no data leaves the machine.

**Why this model:**

- Apache 2.0 license — fully open, no restrictions
- 3.8B active params → fast inference (~20-30 tok/s on Apple Silicon)
- Native function calling → structured JSON output without prompt hacking
- 256K context window → can process full pages with surrounding context
- 140+ languages including Dutch
- ~18GB RAM at Q4 quantization, fits comfortably on a 48GB MacBook Pro

**Memory budget (48GB MacBook Pro):**

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

### Fallback: Anthropic API

Set `LLM_PROVIDER=anthropic` for comparison testing or when Ollama is unavailable. The LLM layer is abstracted behind an `LLMProvider` interface so providers can be swapped via environment variable.

### How the LLM fits in the three tiers

- **Tier 1:** No LLM needed — regex + validation only
- **Tier 2:** LLM used selectively for role classification (is this name a public official?) and traceability assessment. Deduce + regex handle primary detection.
- **Tier 3:** LLM is the primary engine — analyzing passages for policy opinions, business sensitivity, oversight implications. This is where most LLM tokens are spent.

---

## Detection Pipeline

### 1. PDF Text Extraction (PyMuPDF)

Extract every text span with its bounding box coordinates using `page.get_text("dict")`. This gives us character-level position data needed to map detected entities back to visual locations in the PDF. Also extract document metadata (date, author) for the five-year rule check.

### 2. Tier 1 Detection: Hard Identifiers (Regex + Validation)

Pattern-match BSN (with 11-proef), IBAN, phone numbers, email addresses, postcodes, license plates, credit card numbers (Luhn check). These are auto-classified with the appropriate Woo article and standard motivation text. No LLM call needed.

### 3. Tier 2 Detection: Contextual Personal Data (Deduce + LLM)

Run Deduce for Dutch de-identification (names, addresses, institutions). For each detected name, check against the organization's public officials reference list. For unmatched names, optionally call the LLM for role classification based on surrounding context. Detect special personal data via medical NER and keyword matching.

### 4. Tier 3 Detection: Content-Level Analysis (LLM)

Send relevant passages (identified by document type heuristics and keyword signals) to the LLM for analysis. The LLM identifies potential policy opinions, business-sensitive information, oversight-related content, and internal deliberation. Output is an annotation with possible grounds and a qualitative analysis — NOT a redaction decision.

For art. 5.2 passages, the LLM additionally provides a fact-vs-opinion assessment.

### 5. Map Detections to PDF Coordinates

Fuzzy-match detected entity text back to the bounding boxes from step 1. Each detection maps to one or more `(page, bbox)` pairs. Tier 1 detections get black overlays (auto-redacted). Tier 2 detections get colored highlights. Tier 3 detections get annotation markers.

### 6. Apply Redactions (after human review)

Using PyMuPDF's `add_redact_annot()` and `apply_redactions()`. Each redaction area shows the applicable Woo article number. Configurable redaction color per ground. This operation is irreversible — always work on a copy. Originals are stored permanently in MinIO.

---

## LLM System Prompt

The system prompt covers two distinct tasks:

**Task A — Role classification (Tier 2):** Determine whether a detected person name is a citizen, a civil servant not acting publicly, or a public official acting in capacity. Rules include: burgemeester, wethouders, gemeentesecretaris, raadsleden, mandate signatories → don't redact. Private citizens, non-public civil servants → redact.

**Task B — Content analysis (Tier 3):** Analyze passages for potential redaction grounds. Key rules:
- Art. 5.2: distinguish facts from opinions. "Ik adviseer..." = likely opinion. "Het budget bedraagt..." = fact. Facts may NOT be redacted under 5.2.
- Art. 5.1.2f: is the business information competitively sensitive? Was it provided confidentially?
- Art. 5.1.2d: would disclosure impair effective oversight?
- Art. 5.1.2i: would disclosure impair frank internal deliberation?

Output is always structured: possible grounds with qualitative labels, analysis text in Dutch, and for art. 5.2 a fact/opinion classification per sentence.

---

## Database Schema

Six tables:

- **`dossiers`** — Woo request dossiers (title, request number, status: open → in_review → completed, organization name)
- **`documents`** — PDFs within a dossier (filename, MinIO keys for original + redacted, page count, document date for 5-year rule, status: uploaded → processing → review → approved → exported)
- **`detections`** — Detected entities/passages with classification (entity text/type, position coordinates, source, tier [1/2/3], confidence, Woo article, review status: auto_accepted → accepted → rejected → edited → deferred, reviewer info, propagated_from reference for name propagation)
- **`public_officials`** — Reference list of names per organization that should NOT be redacted (importable CSV, linked to dossier or organization)
- **`audit_log`** — Full audit trail (action, actor, details as JSONB)
- **`motivation_texts`** — Generated motivation texts per detection, editable by reviewer, exportable for the Woo decision document

---

## Frontend: Pages & Flow

### Page structure

```
/                           Landing page (public, woobuddy.nl)
/try                        Quick single-PDF upload — no account needed
/app                        Dashboard / dossier list
/app/dossier                Create new dossier
/app/dossier/[id]           Dossier detail: document list, upload, public officials list
/app/dossier/[id]/review/[docId]   ← THE main review interface
/app/export/[dossierId]     Export: redacted PDFs + motivation report
```

### Landing page (`/`)

Single-scroll page. Language: Dutch. No authentication required.

**Sections (top to bottom):**

1. **Header** — Logo (`ShieldCheck` + "WOO Buddy"), CTA button "Probeer gratis"
2. **Hero** — Tagline "Woo-documenten lakken? Laat je buddy het zware werk doen." followed by a short value proposition paragraph. Primary CTA: drag-and-drop PDF upload area. Uploading redirects to `/try`.
3. **"Hoe werkt het?"** — Four steps in a horizontal row: Upload → Detectie → Review → Export. Each with an icon, title, and short description.
4. **"Wat herkent WOO Buddy?"** — Grid of entity type cards: Namen, BSN-nummers, E-mailadressen, Telefoonnummers, Adressen, IBAN-nummers. Plus a closing line about additional types.
5. **"Jij blijft in controle"** — Explains the three-tier model in user-friendly terms: some things are auto-redacted (you can undo), some are suggested (you confirm), some are flagged (you decide with our help).
6. **"Open source & zelf hosten"** — Self-hostable, data stays on your servers, one docker-compose command. Links to GitHub, docs.
7. **Footer** — Logo, links, MIT license.

**Visual feel:** Light, airy, generous whitespace, soft shadows, rounded corners.

### Quick Try page (`/try`)

Accepts upload from the landing page. Shows processing progress. Auto-creates a temporary dossier. When detection completes, redirects to the full review interface.

### Dossier detail page (`/app/dossier/[id]`)

Document list, upload area, and a section for managing the **public officials reference list** — upload a CSV of names that should not be redacted for this organization/dossier.

Also shows dossier-level statistics: documents processed, detections by tier, detections by status (pending/accepted/rejected/deferred), detections by Woo article.

### Review Interface (`/app/dossier/[id]/review/[docId]`)

This is where the reviewer spends 95% of their time. Two-column layout, but the right column adapts based on which tier of detection is selected.

**Left column: PDF preview**
- Renders pages with pdf.js
- Three visual states for overlays:
  - **Black bars** = Tier 1, auto-redacted (with small type icon)
  - **Colored highlight** = Tier 2, pending confirmation (yellow/amber)
  - **Annotation marker** = Tier 3, flagged for review (subtle sidebar indicator, not an overlay)
- Accepted Tier 2 detections transition to black bars
- Rejected detections show a faint green outline (indicating reviewed, kept visible)
- Clicking an overlay scrolls the sidebar to the corresponding detection

**Right column: Detection sidebar — adapts per tier**

*When a Tier 1 detection is selected:*
- Minimal card: entity type, article code, "Auto-gelakt"
- Single button: "Ontlakken" (un-redact) — for exceptional cases

*When a Tier 2 detection is selected:*
- Entity text highlighted in context snippet (±100 chars)
- Entity type badge, proposed Woo article badge
- Confidence indicator (high/medium/low)
- Reasoning: "Persoonsnaam. Niet gevonden in lijst publieke functionarissen."
- Accept (✓ Lakken) / Reject (✗ Niet lakken) buttons
- If accepted: all other occurrences of the same name are auto-accepted (with undo)

*When a Tier 3 annotation is selected:*
- Full decision panel:
  - Possible applicable grounds, ranked
  - Analysis text explaining why flagged
  - For art. 5.2: fact-vs-opinion indicator per sentence
  - Relevant legal text (collapsible)
  - For relative grounds: interest-weighing checklist
  - Three buttons: Redact (select ground) / Don't redact (note why) / Defer (for colleague/jurist)
  - Editable motivation text field

**Bottom toolbar:**
- Progress bar per tier: "Trap 1: 34/34 ✓ | Trap 2: 8/14 | Trap 3: 1/5"
- Batch actions: "Accept all Tier 1", "Accept all high-confidence Tier 2"
- Keyboard shortcuts: `A` accept, `R` reject, `D` defer, `→`/`←` next/prev, `?` help

### Export page (`/app/export/[dossierId]`)

In addition to the redacted PDF ZIP:
- **Motivation report** — structured document exportable as PDF, usable as appendix to the formal Woo decision:
  - Per document: which passages were redacted and on which ground
  - Per Woo article: bundled motivation text
  - For relative grounds: the interest-weighing outcomes
  - Statistics: total passages, per ground, per tier

### Key components

| Component | Purpose |
|-----------|---------|
| `<PdfViewer>` | pdf.js rendering with tier-differentiated overlays |
| `<Tier1Card>` | Minimal auto-redact card with un-redact option |
| `<Tier2Card>` | Suggestion card with context, confidence, accept/reject |
| `<Tier3Panel>` | Full decision support panel with analysis, checklists |
| `<DetectionList>` | Filtered/sorted list, grouped by tier |
| `<DetectionFilters>` | Filter by tier, confidence, entity type, status, page |
| `<NamePropagation>` | Shows propagated decisions, allows undo |
| `<OfficialsList>` | Manage public officials reference list per dossier |
| `<FactOpinionIndicator>` | Visual indicator for art. 5.2 analysis |
| `<InterestWeighingChecklist>` | Structured checklist for relative grounds |
| `<MotivationEditor>` | Editable motivation text per detection |
| `<FileUpload>` | Shared drag-and-drop upload (landing + app) |
| `<ProgressBar>` | Per-tier progress tracking |
| `<KeyboardShortcutHandler>` | Global keyboard shortcuts |

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

PATCH  /api/detections/:id                  Update single detection (accept/reject/defer/edit)
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

## Project Structure

```
woobuddy/
├── docker-compose.yml
├── .env.example
├── README.md
├── THIRD_PARTY_LICENSES.md
├── frontend/
│   ├── package.json
│   ├── svelte.config.js
│   ├── tailwind.config.js
│   ├── vite.config.ts
│   ├── src/
│   │   ├── app.html
│   │   ├── app.css                         Tailwind + Shoelace theme overrides
│   │   ├── lib/
│   │   │   ├── api/client.ts               Typed API client
│   │   │   ├── components/
│   │   │   │   ├── landing/
│   │   │   │   │   ├── Hero.svelte
│   │   │   │   │   ├── HowItWorks.svelte
│   │   │   │   │   ├── WhatWeDetect.svelte
│   │   │   │   │   ├── YouDecide.svelte
│   │   │   │   │   ├── OpenSource.svelte
│   │   │   │   │   └── Footer.svelte
│   │   │   │   ├── shared/
│   │   │   │   │   ├── Logo.svelte
│   │   │   │   │   ├── FileUpload.svelte
│   │   │   │   │   └── ProcessingStatus.svelte
│   │   │   │   ├── review/
│   │   │   │   │   ├── PdfViewer.svelte
│   │   │   │   │   ├── Tier1Card.svelte
│   │   │   │   │   ├── Tier2Card.svelte
│   │   │   │   │   ├── Tier3Panel.svelte
│   │   │   │   │   ├── DetectionList.svelte
│   │   │   │   │   ├── DetectionFilters.svelte
│   │   │   │   │   ├── NamePropagation.svelte
│   │   │   │   │   ├── FactOpinionIndicator.svelte
│   │   │   │   │   ├── InterestWeighingChecklist.svelte
│   │   │   │   │   ├── MotivationEditor.svelte
│   │   │   │   │   ├── BatchActions.svelte
│   │   │   │   │   ├── ProgressBar.svelte
│   │   │   │   │   └── KeyboardShortcuts.svelte
│   │   │   │   ├── dossier/
│   │   │   │   │   ├── DossierCard.svelte
│   │   │   │   │   ├── OfficialsList.svelte
│   │   │   │   │   └── DossierStats.svelte
│   │   │   │   └── export/
│   │   │   │       └── MotivationReport.svelte
│   │   │   ├── stores/
│   │   │   │   ├── detections.ts           Svelte 5 runes-based
│   │   │   │   ├── review.ts
│   │   │   │   └── officials.ts            Public officials reference list
│   │   │   ├── types/index.ts
│   │   │   └── utils/
│   │   │       ├── confidence.ts
│   │   │       ├── tiers.ts                Tier classification helpers
│   │   │       └── woo-articles.ts         All Woo articles with descriptions
│   │   └── routes/
│   │       ├── +layout.svelte
│   │       ├── +page.svelte                Landing page
│   │       ├── try/+page.svelte            Quick try
│   │       └── app/
│   │           ├── +layout.svelte          App shell (sidebar, nav)
│   │           ├── +page.svelte            Dashboard
│   │           ├── dossier/
│   │           │   ├── +page.svelte
│   │           │   └── [id]/
│   │           │       ├── +page.svelte
│   │           │       └── review/[docId]/+page.svelte
│   │           └── export/[dossierId]/+page.svelte
│   └── static/favicon.svg
├── backend/
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── app/
│   │   ├── main.py                         FastAPI app factory
│   │   ├── config.py                       Settings from env
│   │   ├── api/
│   │   │   ├── dossiers.py
│   │   │   ├── documents.py
│   │   │   ├── detections.py
│   │   │   ├── officials.py                Public officials CRUD
│   │   │   └── export.py
│   │   ├── models/schemas.py               SQLAlchemy models
│   │   ├── services/
│   │   │   ├── pdf_engine.py               Extraction + redaction
│   │   │   ├── ner_engine.py               Deduce + regex (Tier 1 + 2)
│   │   │   ├── llm_engine.py               LLM analysis (Tier 2 classification + Tier 3)
│   │   │   ├── propagation.py              Name propagation logic
│   │   │   ├── motivation.py               Motivation text generation
│   │   │   └── export_engine.py            ZIP + motivation report generation
│   │   ├── llm/
│   │   │   ├── provider.py                 Abstract LLMProvider
│   │   │   ├── ollama.py                   Ollama + Gemma 4
│   │   │   ├── anthropic.py                Anthropic fallback
│   │   │   └── prompts.py                  System prompts for Tier 2 + Tier 3
│   │   └── db/
│   │       ├── session.py
│   │       └── migrations/                 Alembic
│   └── tests/
│       ├── test_ner_engine.py
│       ├── test_pdf_engine.py
│       ├── test_propagation.py
│       └── fixtures/sample_woo_document.pdf
└── docs/
    ├── ARCHITECTURE.md
    ├── WOO_ARTICLES.md                     All articles with detection approach per tier
    └── DRIETRAPSRAKET.md                   The three-tier model explained
```

---

## Environment Variables

```env
# LLM Provider
LLM_PROVIDER=ollama                    # "ollama" (default) or "anthropic"

# Ollama (primary — local)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma4:26b
OLLAMA_KEEP_ALIVE=-1                   # Prevent model unloading

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

---

## Design Direction

### Two moods

- **Landing page**: Warm, inviting, generous whitespace, soft colors, rounded corners, friendly Dutch copy.
- **App / review interface**: Professional, dense-but-clear, utilitarian. Optimized for speed and decision-making.

### Color palette

| Role | Color | Usage |
|------|-------|-------|
| Background | `#FAFBFC` | Page backgrounds |
| Primary | `#1B4F72` | Rijksoverheid-blue, trust |
| Primary-light | `#2E86C1` | Hover states, landing accents |
| Danger/Redact | `#C0392B` | "This will be hidden" |
| Success/Keep | `#27AE60` | "This stays visible" |
| Warning/Review | `#F39C12` | "Needs your attention" |
| Neutral | `#5D6D7E` | Secondary text |
| Landing accent | `#EBF5FB` | Card backgrounds on landing |

### Tier-specific visual language

| Tier | PDF overlay | Sidebar indicator | Color |
|------|------------|-------------------|-------|
| Tier 1 (auto-redacted) | Black bar with article code | Compact card, muted | Dark gray/black |
| Tier 2 (suggestion) | Colored highlight | Standard card with accept/reject | Amber/yellow |
| Tier 3 (annotation) | Subtle margin marker | Full analysis panel | Blue/primary |

### Entity type color coding (for Tier 2 badges)

| Entity type | Color | Shoelace variant |
|------------|-------|-----------------|
| persoon | Blue | `primary` |
| bsn | Red | `danger` |
| telefoonnummer | Orange | `warning` |
| email | Orange | `warning` |
| adres | Purple | custom |
| iban | Red | `danger` |
| gezondheid | Dark red | `danger` |
| datum | Gray | `neutral` |

### Typography

System font stack for the app. One distinctive display font for the landing page hero (e.g., `Outfit` or `Plus Jakarta Sans` via Google Fonts). Body text stays system fonts.

### Logo

Lucide `ShieldCheck` as placeholder, rendered as: shield icon in primary color + "WOO" bold + "Buddy" regular weight.

### Shoelace theme overrides

```css
:root {
  --sl-color-primary-600: #1B4F72;
  --sl-color-success-600: #27AE60;
  --sl-color-danger-600: #C0392B;
  --sl-color-warning-600: #F39C12;
  --sl-font-sans: system-ui, -apple-system, sans-serif;
  --sl-border-radius-medium: 6px;
}
```

---

## Build Phases

### Phase 1: Landing page + walking skeleton

1. Docker Compose setup (frontend + api + postgres + minio)
2. **Landing page** — all sections, including three-tier explanation
3. `<FileUpload>` component (shared between landing and app)
4. `/try` page — upload, processing status, auto-create temp dossier
5. FastAPI health endpoint, CORS
6. PDF upload → MinIO → display in PdfViewer
7. Basic dossier CRUD
8. App layout with sidebar nav

### Phase 2: Tier 1 + Tier 2 detection

1. `ner_engine.py` — Deduce + all regex patterns for Tier 1
2. `pdf_engine.py` — text extraction with bounding boxes + document date
3. Tier 1 auto-classification (no LLM)
4. Tier 2 detection via Deduce NER
5. `llm_engine.py` — Ollama provider for Tier 2 role classification
6. Public officials reference list (CSV upload, matching logic)
7. `POST /api/documents/:id/detect` endpoint
8. Store detections in PostgreSQL with tier classification

### Phase 3: Review interface (Tier 1 + Tier 2)

1. `<Tier1Card>` — minimal auto-redact with un-redact
2. `<Tier2Card>` — suggestion with context, confidence, accept/reject
3. `<DetectionList>` with tier-aware filtering/sorting
4. `<PdfViewer>` with tier-differentiated overlays
5. **Name propagation** — accept once, propagate across dossier
6. PATCH endpoint for detection review
7. Keyboard shortcuts
8. Batch actions (per tier)

### Phase 4: Tier 3 analysis

1. LLM prompts for content-level analysis (art. 5.2, 5.1.2d, 5.1.2f, 5.1.2i)
2. `<Tier3Panel>` — full decision support panel
3. `<FactOpinionIndicator>` for art. 5.2
4. `<InterestWeighingChecklist>` for relative grounds
5. `<MotivationEditor>` — editable motivation text
6. Defer/later-review workflow

### Phase 5: Export + audit

1. `apply_redactions()` with PyMuPDF (configurable redaction color)
2. **Motivation report generator** — structured PDF appendix for Woo decision
3. Audit logging (every decision: who, when, what, which ground)
4. ZIP export for full dossiers
5. Five-year rule warnings
6. Environmental information detection + restricted grounds flag

### Phase 6: Production hardening

1. Tesseract OCR for scanned PDFs
2. User authentication
3. Celery + Redis for batch processing of large dossiers
4. Accessibility audit (critical for government tooling)
5. Quality comparison with Gemma 4 31B dense model
6. Third-party consultation (zienswijze) flagging

---

## Implementation Notes

1. **Ollama must be running** before starting the backend. FastAPI lifespan should verify Ollama connectivity and check that a `gemma4` model is available on startup.

2. **Ollama on macOS vs Docker**: On macOS, run Ollama natively for Apple Silicon performance. Docker containers reach it via `host.docker.internal:11434`. On Linux, either run natively or add the `ollama` service to docker-compose.

3. **Function calling**: Use Ollama's `/api/chat` with the `tools` parameter. Define separate tools for Tier 2 (role classification) and Tier 3 (content analysis). Gemma 4 calls them with structured parameters.

4. **Shoelace SSR**: Web components need the browser's `customElements` API. Wrap imports in `onMount()` or use dynamic imports. Consider `export const ssr = false;` for the review page.

5. **pdf.js worker**: Exclude from Vite's optimizeDeps: `optimizeDeps: { exclude: ['pdfjs-dist'] }`.

6. **Deduce initialization**: Loads lookup tables on first use (~2s). Initialize once in FastAPI lifespan, not per-request.

7. **Confidence boosting**: When Deduce and regex both flag the same entity, boost confidence. When only one flags it, reduce. When the LLM disagrees with rule-based detection, surface it prominently to the reviewer.

8. **Redaction is permanent**: `page.apply_redactions()` cannot be undone. Always work on a copy. Store originals permanently in MinIO.

9. **Keep Ollama warm**: Set `OLLAMA_KEEP_ALIVE=-1` to prevent model unloading. Reloading takes 15-30 seconds.

10. **Shoelace events in Svelte 5**: Use the `onsl-*` pattern: `<sl-button onsl-focus={(e) => handle(e)}>`.

11. **Name propagation must be undoable**: When a name decision propagates across a dossier, all propagated decisions should link back to the source decision and be reversible with a single action.

12. **Tier 3 should NOT show confidence percentages**: Use qualitative labels ("Mogelijk persoonlijke beleidsopvatting") instead. Percentages are misleading for content-level judgments.

13. **Deduce is LGPL-3.0 licensed**: Compatible with MIT when used as a pip dependency. Include its license in `THIRD_PARTY_LICENSES.md`.
