# WOO Buddy — Todo Backlog

> **2026-04 reprioritization** — The backlog was reordered to put the **core redaction experience first**, then **UX polish**, and only then product-layer features like auth, billing, and analytics. The goal is a prototype that blows people away before we wrap it in a SaaS. See "Guiding philosophy" below.

## Guiding philosophy

**1. Core functionality first.** The prototype has to feel great at the one thing it does: helping a Woo reviewer redact a document. That means manual text selection, area selection, undo, search-and-redact, and page completeness land before anything else. If a reviewer can't trust and enjoy the editing loop, nothing downstream matters.

**2. Then polish.** Loading states, animations, and mobile responsiveness come right after core editing. The demo has to look and feel great, not just work.

**3. Only then, the SaaS layer.** Authentication, organizations, roles, billing, analytics, deployment hardening — all deferred until the core experience is compelling. Today the app is single-document and runs locally; that's fine for a prototype and for pilot demos.

**4. Privacy-first: client-side wherever possible, ephemeral on the server where unavoidable.** This project is being built for Dutch government users handling privacy-sensitive documents. The trust story must be simple and defensible:

- **PDFs never leave the browser** (except for ephemeral, in-memory redaction during export).
- **Extracted text** is sent to the server only for detection (NER + local LLM). The server processes it in memory and discards it — nothing is logged, nothing is persisted.
- **The database stores decisions, not content.** Bbox coordinates, article references, review status — no `entity_text`, no document bodies, no export artifacts.
- **We accept limitations this imposes.** Draft-saving, cross-session resume, and server-side previews are harder (or impossible) under this model. That is a deliberate trade-off. When a feature seems to require server-side document storage, the right answer is usually "keep it in IndexedDB" or "drop the feature" — not "compromise the privacy story."
- **The self-hosted LLM is the one unavoidable server touchpoint for content.** It runs locally (Ollama + Gemma), sees extracted text ephemerally, and never persists it. This is the model for anything else that genuinely needs server-side processing: keep it local, keep it ephemeral, keep it out of the logs.

Full architectural specification: [#00 — Client-first architecture](done/00-client-first-architecture.md).

---

## Prioritization System

Each todo file has a **priority**, **size**, and **phase** in its frontmatter.

### Priority

| Level | Meaning | Guideline |
|-------|---------|-----------|
| **P0** | Must have before any real users | Security, data integrity, core workflow gaps |
| **P1** | Must have for pilot / beta launch | Key features that real reviewers need daily |
| **P2** | Should have for public SaaS launch | Business features, oversight, polish |
| **P3** | Nice to have / future | Enhancements, optimizations, minor UX |

### Size (estimated effort)

| Size | Meaning |
|------|---------|
| **S** | < 1 day |
| **M** | 1–3 days |
| **L** | 3–7 days |
| **XL** | 1–2 weeks |

### Implementation Order

Work top-to-bottom within each phase. Higher-priority items within a phase come first.
Dependencies are noted in each file — don't start a blocked item before its dependency is done.

---

## Phase A — Foundation (architecture + hardening)

Small security/logging work on top of the already-done client-first architecture and testing foundation.

| # | Todo | Priority | Size | Source |
|---|------|----------|------|--------|
| 0 | ~~[Client-first architecture](done/00-client-first-architecture.md)~~ | P0 | XL | Architectural decision |
| 1 | ~~[Testing foundation](done/01-testing-foundation.md)~~ | P0 | L | Testing & Polish |
| 2 | ~~[Error handling](done/02-error-handling.md)~~ | P0 | M | Testing & Polish |
| 3 | ~~[Security hardening](done/03-security-hardening.md)~~ | P0 | M | Testing & Polish |
| 4 | ~~[Structured logging](done/04-structured-logging.md)~~ | P1 | S | Testing & Polish |

## Phase B — Core Redaction Experience (the prototype's reason for existing)

This phase turns the viewer into an actual editing tool. **Everything here must respect the client-first architecture** — manual detections live in IndexedDB first; server metadata sync is secondary and can be stubbed/deferred if it slows us down.

| # | Todo | Priority | Size | Source |
|---|------|----------|------|--------|
| 5 | ~~[Review/Edit mode toggle](done/05-mode-toggle.md)~~ | P1 | M | Editing |
| 6 | ~~[Manual text selection redaction](done/06-manual-text-redaction.md)~~ | P1 | L | Editing |
| 7 | ~~[Area selection redaction](done/07-area-selection.md)~~ | P1 | M | Editing |
| 8 | ~~[Undo/redo](done/08-undo-redo.md)~~ | P1 | M | Editing |
| 9 | ~~[Search-and-redact](done/09-search-and-redact.md)~~ | P1 | L | Editing |
| 10 | [Page completeness review](10-page-completeness.md) | P1 | M | Editing |
| 11 | [Boundary adjustment](11-boundary-adjustment.md) | P2 | L | Editing |
| 12 | [Split and merge detections](12-split-merge.md) | P3 | M | Editing |

## Phase C — Polish & UX (make the prototype feel premium)

Once the core loop works, make it feel great. This is the "wow moment" phase — the tool should look and behave like a product, not an engineering demo.

| # | Todo | Priority | Size | Source |
|---|------|----------|------|--------|
| 13 | [Loading states & skeletons](13-loading-states.md) | P2 | M | Testing & Polish |
| 14 | [Landing page animations](14-animations.md) | P3 | S | Testing & Polish |
| 15 | [Mobile responsive polish](15-mobile-responsive.md) | P3 | S | Testing & Polish |

## Phase D — Draft Workflow & Oversight

Supervisors, jurists, and multi-step approval. Note: several items here presuppose a multi-user / persistent-draft model, so they may need to be revisited under the client-first constraint (drafts live in IndexedDB, approval is a metadata flag). Revisit scope before starting each item.

| # | Todo | Priority | Size | Source |
|---|------|----------|------|--------|
| 16 | [Document lifecycle (draft/approve)](16-document-lifecycle.md) | P1 | M | Draft Workflow |
| 17 | [Redaction log](17-redaction-log.md) | P2 | L | Draft Workflow |
| 18 | [Draft preview & side-by-side](18-draft-preview.md) | P2 | M | Draft Workflow |
| 19 | [Draft comments](19-draft-comments.md) | P3 | M | Draft Workflow |

## Phase E — Export Enhancements

| # | Todo | Priority | Size | Source |
|---|------|----------|------|--------|
| 20 | [Export versioning & re-export](20-export-versioning.md) | P2 | M | Draft Workflow |
| 21 | [Concept export with watermark](21-concept-export.md) | P2 | S | Draft Workflow |
| 22 | [Redaction map generation](22-redaction-map.md) | P3 | M | Draft Workflow |
| 23 | [Redaction inventory (CSV/XLSX)](23-redaction-inventory.md) | P3 | S | Draft Workflow |

## Phase F — Auth & Multi-Tenancy (deferred until the prototype is compelling)

These are deliberately pushed down the stack. Real users need auth eventually, but nothing about the core redaction experience requires it — and `reviewed_by` can remain a text field while the prototype stabilizes. **#25 (Organizations) was written against the old multi-document shape and needs a rewrite before implementation** (the app is currently single-document; see `CLAUDE.md`).

| # | Todo | Priority | Size | Source |
|---|------|----------|------|--------|
| 24 | [Authentication (Better Auth)](24-authentication.md) | P0 | L | Auth & Billing |
| 25 | [Organizations & data scoping](25-organizations.md) | P0 | L | Auth & Billing |
| 26 | [Roles & permissions](26-roles-permissions.md) | P1 | M | Auth & Billing |
| 27 | [Member management & invitations](27-member-management.md) | P2 | M | Auth & Billing |

## Phase G — SaaS Launch (billing, email, deployment, legal, analytics)

Everything a SaaS needs but a prototype does not.

| # | Todo | Priority | Size | Source |
|---|------|----------|------|--------|
| 28 | [Mollie billing integration](28-mollie-billing.md) | P2 | XL | Auth & Billing |
| 29 | [Email service](29-email-service.md) | P2 | M | Testing & Polish |
| 30 | [Deployment setup](30-deployment.md) | P2 | M | Testing & Polish |
| 31 | [Legal pages & SEO](31-legal-seo.md) | P2 | S | Testing & Polish |
| 32 | [Analytics (Plausible)](32-analytics.md) | P3 | S | Testing & Polish |
| 33 | [Microsoft SSO & 2FA](33-sso-2fa.md) | P3 | M | Auth & Billing |

---

## Briefings Not Adopted (or deferred)

Some briefing suggestions are **deferred or modified**:

- **Server-side PDF storage** (all briefings) — Replaced by client-first architecture (#00). PDFs never persist on the server.
- **MinIO as document store** (main briefing) — Removed or reduced to optional temporary artifact storage. See #00.
- **`entity_text` in database** (all briefings) — Detection records store positions and types, not the actual sensitive text. See #00.
- **Subscription tier pricing** (Auth & Billing) — The specific price points (49/149/349) are business decisions, not engineering tasks. Captured in the billing todo as configurable, not hardcoded.
- **Celery job queue** (Draft Workflow) — Overkill for MVP. Background tasks via FastAPI's built-in `BackgroundTasks` suffice until proven otherwise.
- **Full fuzzy name matching** (Editing) — Simplified to basic normalization for Phase B. Full Dutch name-particle matching is a P3 enhancement.
- **Self-hosted version** (Auth & Billing) — Briefing correctly says "should not complicate the architecture now." Agreed, not tracked.

## How to Use This Backlog

1. Pick the current phase (A → B → C → ...)
2. Work through todos within the phase in order
3. A todo is "done" when its acceptance criteria are met — then move the file to `done/` and update this index
4. Cross-phase dependencies are noted — respect them
5. P3 items within a phase can be skipped and revisited later
6. **Every todo must respect the client-first architecture in #00** — if a feature seems to require server-side document storage, the design is wrong; revisit before implementing
