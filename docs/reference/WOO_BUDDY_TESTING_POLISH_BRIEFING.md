# WOO Buddy — Supplementary Briefing: Testing, Polish & Operational Gaps

## What This Covers

The existing four briefings define what to build. This briefing covers how to test it, how to make it feel good, and what operational infrastructure is missing. These are the gaps that would otherwise be discovered mid-build.

---

## 1. Testing Strategy

### Overview

Three layers, each with a different tool and purpose:

| Layer | Tool | What it tests | Runs when |
|-------|------|--------------|-----------|
| **Unit** | Vitest | Functions, utilities, stores, API logic | Every save (watch mode) |
| **Component** | Vitest Browser Mode + vitest-browser-svelte | Svelte components in a real browser | Pre-commit, CI |
| **E2E** | Playwright | Full user journeys across pages | CI, pre-deploy |

Plus **Python backend tests** with pytest for the FastAPI layer.

### Frontend: Vitest setup

Use Vitest with the **browser mode** powered by Playwright — this runs component tests in a real Chromium instance instead of jsdom. No more mocking browser APIs.

```
pnpm add -D vitest @vitest/browser vitest-browser-svelte @vitest/browser-playwright playwright
```

The Vitest config uses a **multi-project setup**: separate configurations for client-side (browser), server-side (node), and SSR tests. This prevents client tests from accidentally importing server code and vice versa.

Key test files to write first (highest value):

- `woo-articles.test.ts` — verify all article codes, descriptions, and tier classifications are correct and complete
- `confidence.test.ts` — confidence scoring logic (boosting, reducing, thresholds)
- `tiers.test.ts` — tier classification helpers (given an entity type and article, which tier?)
- `DetectionList.svelte.test.ts` — filtering, sorting, grouping behavior
- `Tier2Card.svelte.test.ts` — accept/reject flow, name propagation trigger
- `PdfViewer.svelte.test.ts` — overlay rendering at correct coordinates (mock the pdf.js canvas)

### Frontend: Playwright E2E

Playwright tests cover full user journeys. Critical paths to test:

1. **Signup → upload → review → export**: The golden path. Create account, create org, upload a PDF, process it, review detections, approve, export.
2. **Quick try flow**: Upload from landing page → forced login → resume upload → redirect to review.
3. **Name propagation**: Accept a name in one document, verify it's auto-accepted in another document in the same dossier.
4. **Manual redaction**: Enter edit mode, select text, assign article, verify it appears in the detection list and in the draft preview.
5. **Billing upgrade**: Free tier user hits document limit, sees upgrade prompt, completes Mollie checkout (use Mollie test mode), verifies new limits apply.

Playwright tests should run against a **local Docker Compose stack** with test fixtures pre-loaded. Use Playwright's `globalSetup` to spin up the stack and seed test data.

### Backend: pytest

FastAPI tests use pytest with `httpx.AsyncClient` for async endpoint testing and a test PostgreSQL database (separate from dev).

Key test files:

- `test_ner_engine.py` — Deduce + regex detection on sample texts. Verify BSN detection with valid/invalid 11-proef, IBAN patterns, phone number formats, email patterns, license plates.
- `test_pdf_engine.py` — text extraction from a sample PDF, verify bounding boxes are reasonable. Redaction application on a copy, verify original is untouched.
- `test_llm_engine.py` — mock the Ollama API, verify the function calling request format is correct, verify response parsing handles well-formed and malformed responses.
- `test_propagation.py` — name propagation logic: propagate, undo propagation, propagate across documents.
- `test_billing_middleware.py` — plan limit enforcement: free tier blocks at 3 docs, basis tier allows 50, etc.
- `test_mollie_webhooks.py` — webhook processing for various payment statuses (paid, failed, expired, canceled).

### Test data

Create a `fixtures/` directory with:

- `sample_woo_besluit.pdf` — a realistic Woo decision document with known entities (specific BSN, names, addresses, IBANs placed at known positions)
- `sample_email.pdf` — a PDF-rendered email thread with personal data
- `sample_beslisnota.pdf` — an internal policy memo with opinions and facts mixed
- `expected_detections.json` — the expected output of the detection pipeline for each sample PDF (entity text, type, tier, expected article, approximate bbox)

This lets you write **regression tests**: run the pipeline on a sample PDF, compare the output to the expected detections, flag any differences. As the detection pipeline improves, update the expected output.

### CI pipeline (GitHub Actions)

```yaml
# .github/workflows/test.yml
jobs:
  frontend-unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - run: pnpm install
      - run: pnpm test:unit

  frontend-e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - run: pnpm install
      - run: npx playwright install --with-deps chromium
      - run: docker compose -f docker-compose.test.yml up -d
      - run: pnpm test:e2e

  backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: woobuddy_test
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -e ".[test]"
      - run: pytest
```

Note: E2E tests do NOT require Ollama in CI. Mock the LLM layer for CI. Real LLM testing happens locally during development and in a separate, manual QA step.

---

## 2. Animation & Motion

### Library: `@humanspeak/svelte-motion`

This is the most actively maintained Framer Motion port for Svelte 5. It provides `motion.div`, `motion.button`, etc. with `initial`, `animate`, `exit`, `whileHover`, `whileTap` props and spring physics. It supports SSR (no hydration flicker), stagger via variant propagation, and exit animations via `AnimatePresence`.

```
pnpm add @humanspeak/svelte-motion
```

### Where to use animation (and where not to)

**The landing page** gets the most animation. The app interface gets almost none — speed and clarity win over visual polish when someone is reviewing 200 detections.

#### Landing page animations

**Hero section — staggered entrance:**
The tagline, description paragraph, and upload area fade-and-slide-up in sequence with 100ms delays. Use `motion.div` with variants:

```svelte
<script>
  import { motion } from '@humanspeak/svelte-motion';
</script>

<motion.div
  initial={{ opacity: 0, y: 20 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ duration: 0.5, delay: 0.1 }}
>
  <h1>Woo-documenten lakken?</h1>
</motion.div>

<motion.div
  initial={{ opacity: 0, y: 20 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ duration: 0.5, delay: 0.2 }}
>
  <p>Laat je buddy het zware werk doen.</p>
</motion.div>
```

**Upload area — breathing pulse:**
A subtle CSS animation on the upload drop zone border. Not a library animation — just CSS:

```css
.upload-zone {
  border: 2px dashed var(--sl-color-primary-400);
  animation: breathe 3s ease-in-out infinite;
}

@keyframes breathe {
  0%, 100% { border-color: var(--sl-color-primary-300); }
  50% { border-color: var(--sl-color-primary-600); }
}
```

When a file is dragged over, the zone scales up slightly and the border goes solid:

```css
.upload-zone.drag-over {
  transform: scale(1.02);
  border-style: solid;
  border-color: var(--sl-color-primary-600);
  background: var(--sl-color-primary-50);
  transition: all 0.15s ease;
}
```

**"Hoe werkt het?" steps — scroll reveal with stagger:**
Use IntersectionObserver (no library needed) to trigger a CSS class when the section scrolls into view. Each step card gets a staggered `animation-delay`:

```css
.step-card {
  opacity: 0;
  transform: translateY(24px);
  transition: opacity 0.5s ease, transform 0.5s ease;
}

.step-card.visible {
  opacity: 1;
  transform: translateY(0);
}

.step-card:nth-child(1) { transition-delay: 0ms; }
.step-card:nth-child(2) { transition-delay: 100ms; }
.step-card:nth-child(3) { transition-delay: 200ms; }
.step-card:nth-child(4) { transition-delay: 300ms; }
```

**Entity type cards grid — same scroll-reveal pattern** with stagger.

#### App interface animations

Keep these minimal and fast. They should feel responsive, not decorative.

**Detection card accept/reject:** When the reviewer clicks ✓ or ✗, the card briefly flashes green (accepted) or red (rejected), then smoothly transitions to its resolved visual state. Use a 200ms CSS transition — no library needed.

**Tier 1 auto-redact appearance:** When a document first loads and Tier 1 detections are shown as black bars, animate them in with a quick fade (150ms). This gives the reviewer a moment to register "these are the auto-redactions" before diving in.

**Detection list filtering:** When filters change and items are added/removed from the list, use Svelte 5's built-in `animate:flip` for smooth list reordering. No external library needed.

**Mode toggle (Review ↔ Edit):** When switching modes, briefly pulse the toolbar's mode indicator (100ms background color transition). This is a micro-confirmation that the mode changed.

**Undo flash:** When an undo occurs, the affected area in the PDF viewer gets a 300ms highlight pulse (yellow flash → fade out). CSS-only.

**Progress bar increments:** The per-tier progress bar in the bottom toolbar uses CSS `transition: width 0.3s ease` so it smoothly grows as detections are resolved.

#### What NOT to animate

- Detection sidebar scrolling — instant, no smooth scroll (speed > prettiness)
- PDF page transitions — instant render, no fade between pages
- Anything in the redaction log table — data tables should never animate
- Draft preview rendering — instant, the overlay must appear immediately as decisions change
- Any batch operation result — if 50 detections are accepted at once, show the result immediately, don't animate 50 cards

### `prefers-reduced-motion`

Wrap all animations in a media query check. Users who have "reduce motion" enabled in their OS should see instant state changes with no animation:

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

This is particularly important for a government tool — accessibility is not optional.

---

## 3. Error Handling

The briefings describe the happy path. Here's what happens when things go wrong:

### Ollama is down or unreachable

- FastAPI checks Ollama connectivity on startup. If unreachable, log a warning but **don't crash** — Tier 1 and Tier 2 (NER) detection still work without the LLM.
- When a detection pipeline runs and the LLM call fails: mark Tier 2 role classifications as "unclassified" (reviewer sees "Kon niet automatisch worden geclassificeerd — beoordeel handmatig") and skip Tier 3 analysis entirely.
- Show a **banner** in the app UI: "LLM-analyse is momenteel niet beschikbaar. Trap 1 en 2 detecties werken normaal." Dismissable, but reappears if the user navigates to a document.

### PDF is corrupt or unreadable

- PyMuPDF fails to open → return a clear error: "Dit PDF-bestand kon niet worden geopend. Het bestand is mogelijk beschadigd."
- PyMuPDF opens but text extraction returns nothing (scanned PDF without OCR) → warn the user: "Dit document bevat geen selecteerbare tekst. Mogelijk is het een scan. Handmatige lakking is nog steeds mogelijk." Still allow manual redaction via area selection.
- PDF is password-protected → "Dit document is beveiligd met een wachtwoord. Voer het wachtwoord in om door te gaan." (Password input field.)

### File too large

- Set a **max upload size** of 50MB per file (configurable). Larger files are rejected at the FastAPI level with a clear message.
- For very large PDFs (100+ pages), show a warning: "Dit document heeft [X] pagina's. Verwerking kan enkele minuten duren."

### Network errors during review

- All API calls from the frontend should have **retry logic** (1 retry after 2s delay for transient failures).
- If the API is unreachable, show an inline error on the specific operation that failed ("Kon de detectie niet bijwerken. Probeer opnieuw.") with a retry button. Don't show a full-page error.
- Unsaved changes should be buffered in the browser. If the reviewer accepts 5 detections and then the network drops, the acceptances should be queued and synced when the connection returns. Use a simple queue in a Svelte store.

### Mollie payment failures

- If a first payment is created but never completed (user abandons Mollie checkout): the organization stays on the free tier. No action needed.
- If a recurring payment fails: Mollie does not retry. After a 7-day grace period, downgrade the organization to the free tier. Send an email notification at: payment failure, 3 days before downgrade, and at downgrade.
- Existing dossiers are preserved (read-only) after downgrade. The user sees: "Je abonnement is verlopen. Upgrade om nieuwe documenten te verwerken. Je bestaande dossiers blijven beschikbaar."

---

## 4. Email Service

Better Auth needs to send emails for verification, password reset, and organization invitations. The Mollie billing flow needs emails for payment receipts and failure notifications.

### Recommendation: Resend

**Resend** is a developer-friendly transactional email service. European data processing available. Simple API, good SvelteKit/Node.js SDK.

Alternative if you want EU-only: **Scaleway Transactional Email** (French, fully EU) or **Mailgun EU** (Rackspace, EU region available).

For prototype/dev: use **Nodemailer** with any SMTP provider (Gmail SMTP works for testing). Swap to Resend for production.

### Email templates needed

| Email | When | Content |
|-------|------|---------|
| Verify email | After signup | "Bevestig je e-mailadres" + verification link |
| Password reset | User requests reset | "Wachtwoord herstellen" + reset link |
| Organization invitation | Admin invites a member | "[Org name] nodigt je uit voor WOO Buddy" + accept link |
| Payment successful | After Mollie payment | "Betaling ontvangen" + receipt details |
| Payment failed | Mollie webhook: failed | "Betaling mislukt" + retry/update payment method link |
| Downgrade warning | 3 days before grace period ends | "Je abonnement verloopt binnenkort" + upgrade link |
| Account downgraded | After grace period | "Je account is teruggezet naar Gratis" + upgrade link |

All emails should be in Dutch, plain and professional. HTML templates with the WOO Buddy logo and a single CTA button. No marketing fluff.

---

## 5. Deployment

### Hosting recommendation: Railway or Fly.io

For a SaaS MVP, use a platform that handles containers and PostgreSQL without requiring infrastructure expertise. **Railway** is the simplest: push to GitHub, it deploys. PostgreSQL as a managed addon. Supports multiple services (frontend, API) in one project.

**Fly.io** is an alternative with more control and European regions (Amsterdam).

Either way, the deployment is:
- SvelteKit frontend (Node.js adapter) → one service
- FastAPI backend → one service
- PostgreSQL → managed database addon
- MinIO → either a managed S3-compatible service (Cloudflare R2, Backblaze B2) or a MinIO container

Ollama does NOT run on the hosting platform in production. For the SaaS version, the LLM inference needs a GPU machine. Options:
- A dedicated GPU VPS (Hetzner GPU servers, ~€150/month for an RTX 3090) running Ollama, accessed by the FastAPI backend over a private network
- Or use the Anthropic API fallback for production (simpler, but adds per-token cost and sends document text to Anthropic)

This is a key decision to make before production launch. For the prototype, running Ollama locally on your MacBook Pro works.

### Domain and DNS

- Register `woobuddy.nl` at a Dutch registrar (TransIP, Antagonist, or your existing provider)
- Point DNS to the hosting platform
- SSL is handled automatically by the platform (Let's Encrypt)

---

## 6. Loading States & Skeleton Screens

The review interface loads complex data. Every loading state needs to feel intentional, not broken.

### Upload → processing

The `/try` and dossier upload flow shows a multi-step progress indicator:

```
[✓ Uploaden]  →  [● Tekst extraheren]  →  [○ Detectie]  →  [○ Classificatie]
```

Each step transitions from empty circle → filled/active → checkmark as it completes. Use Shoelace's `<sl-progress-bar>` with indeterminate mode during each step, switching to determinate when the step count is known.

### Review interface initial load

When navigating to the review page, three things load in parallel: the PDF page, the detection list, and the dossier metadata. Show:

- A **skeleton PDF page** (gray rectangle with faint line placeholders) until the page renders
- **Skeleton detection cards** in the sidebar (3-4 gray placeholder cards with shimmer animation) until detections load
- The toolbar and progress bar load immediately with cached or zero state

### Long operations

Any operation that takes more than 500ms should show a loading indicator:

- Detection pipeline (10-60s depending on document size): full progress screen with step indicators
- Export generation (5-30s): progress bar in the export dialog
- Batch operations (1-5s): inline spinner on the batch action button, disabled state until complete
- LLM classification of a single entity (1-2s): subtle spinner on the detection card being classified

---

## 7. Mobile & Responsive

### What works on mobile

- Landing page — fully responsive, single column on small screens
- Auth pages (login, signup) — simple forms, work on any screen
- Dashboard / dossier list — card layout adapts to screen width
- Billing page — straightforward responsive layout
- Organization settings — form-based, works on mobile

### What is desktop-only

- **Review interface** — the two-column layout (PDF + sidebar) requires a wide screen. On screens below 1024px, show a message: "De beoordelingsinterface is geoptimaliseerd voor desktop. Gebruik een groter scherm voor de beste ervaring." With a link to view the dossier in read-only mode.
- **Edit mode** — text selection and boundary adjustment require precise mouse control
- **Redaction log** — complex table with many columns, needs desktop width

### Implementation

Use Tailwind responsive breakpoints. The landing page and simple pages use a fluid layout. The review interface has `min-width: 1024px` on its container and shows the mobile fallback below that breakpoint.

---

## 8. Structured Logging

### Backend (FastAPI)

Use **structlog** for structured JSON logging. Every log entry includes: timestamp, level, request_id, user_id, organization_id, and a message.

Log levels:
- **INFO**: document uploaded, detection pipeline started/completed, detection accepted/rejected, export generated
- **WARNING**: Ollama unreachable, LLM call timeout, Mollie webhook for unknown payment
- **ERROR**: PDF processing failure, database error, unhandled exception

### Frontend (SvelteKit)

Use **Sentry** (or the open-source **GlitchTip**) for error tracking. Capture unhandled exceptions, failed API calls, and performance data. Sentry has a SvelteKit SDK.

For production, set up alerts on: error rate spikes, API response time > 5s, and Ollama health check failures.

---

## 9. Security Hardening

Items not covered in the other briefings:

- **CSRF protection**: SvelteKit has built-in CSRF protection for form actions. For API calls via fetch, the SvelteKit proxy handles this. Ensure the FastAPI backend only accepts requests from the SvelteKit proxy (check a shared secret header or restrict to internal network).
- **Content Security Policy**: Set a strict CSP header. Allow scripts only from the application origin and cdn.jsdelivr.net (for Shoelace). Block inline scripts.
- **Rate limiting**: FastAPI middleware using `slowapi` or a Redis-backed rate limiter. Key rates: 10 signups/hour per IP, 100 API calls/minute per user, 5 file uploads/minute per organization.
- **File validation**: Beyond checking the extension, verify the file is actually a PDF by reading the magic bytes (`%PDF-`). Reject anything else. Run uploaded PDFs through PyMuPDF's `open()` in a try/catch to detect corrupt files before storing in MinIO.
- **Document isolation**: Every database query that touches dossiers, documents, or detections MUST include `WHERE organization_id = :org_id`. This is the single most important security invariant. Consider a PostgreSQL Row-Level Security policy as a defense-in-depth measure.
- **Audit log is append-only**: Never delete or modify audit log entries. This is essential for legal compliance in Woo processes.

---

## 10. Other Missing Pieces

### SEO and meta tags (landing page)

The landing page needs proper meta tags for search engines and social sharing:

```html
<title>WOO Buddy — Jouw slimme assistent voor het lakken van Woo-documenten</title>
<meta name="description" content="Open-source tool die Nederlandse overheidsmedewerkers helpt bij het verwerken van Woo-verzoeken. Detecteert automatisch persoonsgegevens, BSN-nummers en andere privacygevoelige informatie." />
<meta property="og:title" content="WOO Buddy" />
<meta property="og:description" content="Woo-documenten lakken? Laat je buddy het zware werk doen." />
<meta property="og:image" content="https://woobuddy.nl/og-image.png" />
<meta property="og:url" content="https://woobuddy.nl" />
<meta name="twitter:card" content="summary_large_image" />
```

Create an `og-image.png` (1200×630px) showing the WOO Buddy logo, tagline, and a stylized screenshot of the review interface.

### Favicon

Generate a favicon set from the ShieldCheck placeholder logo: favicon.ico, apple-touch-icon.png, favicon-32x32.png, favicon-16x16.png. Use a favicon generator service. Place in `static/`.

### Legal pages

Required for a Dutch SaaS product:

- `/privacy` — Privacyverklaring (Privacy policy). What data is collected, how it's processed, how long it's retained, who has access.
- `/terms` — Algemene voorwaarden (Terms of service). Usage terms, liability, SLA.
- `/cookies` — Cookie policy (minimal — WOO Buddy should only use essential cookies for sessions, no tracking).
- `/verwerkersovereenkomst` — Data processing agreement template. Government organizations will want this before uploading real documents.

These can be simple markdown-rendered pages. Have a lawyer review them before launch.

### Cookie consent

Since WOO Buddy only uses essential session cookies (no analytics, no tracking), a cookie consent banner is technically not required under Dutch law / ePrivacy. But a brief notice in the footer linking to the cookie policy is good practice: "WOO Buddy gebruikt alleen functionele cookies. Meer informatie."

### Analytics

For the landing page only: use **Plausible** (EU-hosted, privacy-friendly, no cookie consent needed) or **Fathom**. Do NOT use Google Analytics — it's inappropriate for a government-facing privacy tool.

Track: page views, "Probeer gratis" button clicks, signup conversion rate, document upload count. Nothing else.
