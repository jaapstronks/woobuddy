# 39 — Deployment Setup

- **Priority:** P2
- **Size:** M (1–3 days)
- **Source:** Testing & Polish briefing, Section 5
- **Depends on:** #01 (Testing — CI should exist before CD), #32 (Auth)
- **Blocks:** Nothing

## Why

The app needs to be accessible on the internet for real users. Deployment infrastructure must be set up before launch.

## Scope

### Hosting platform

- [ ] Choose between Railway (simplest) and Fly.io (EU regions, more control)
- [ ] Configure two services: SvelteKit (Node.js adapter) + FastAPI
- [ ] Managed PostgreSQL addon
- [ ] **No S3/MinIO needed for document storage** — under client-first architecture, PDFs never leave the browser. The only server-side storage is PostgreSQL for metadata. If temporary artifact storage is needed (e.g., dossier ZIP assembly), use ephemeral local storage or a small S3 bucket with auto-expiry.

### Hosting cost profile

- [ ] **No GPU, no LLM inference, no model hosting.** The pipeline is regex + Deduce NER + wordlists (CPU-bound, light). A small EU VPS (Hetzner CX22 or similar, ~€5–10/month) is sufficient for the hosted free tier; managed Postgres adds another ~€15/month. This is what makes the generous free tier in #37 viable.
- [ ] EU region only (Hetzner FSN/NBG, Fly.io AMS/FRA, Railway EU). Document hosting region in the privacy policy (#40).
- [ ] If the dormant LLM layer is ever revived behind its feature flag, GPU hosting becomes a separate cost decision — not part of the default deployment.

### Domain & DNS

- [ ] Register `woobuddy.nl` (Dutch registrar)
- [ ] Point DNS to hosting platform
- [ ] SSL via Let's Encrypt (platform-managed)

### CI/CD

- [ ] GitHub Actions workflow: test → build → deploy on push to main
- [ ] Staging environment for pre-production testing

### Environment management

- [ ] Production environment variables documented and securely stored
- [ ] Separate dev/staging/production configs

## Acceptance Criteria

- App is accessible at `woobuddy.nl` with HTTPS
- Deployments happen automatically on push to main
- Database is backed up on a schedule
- Hosting region is EU-only and documented in the privacy policy
- No PDF storage in cloud object storage (PDFs stay in the browser, per #00)
