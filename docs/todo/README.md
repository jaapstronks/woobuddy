# WOO Buddy — Todo Backlog

> **2026-04 pivot — "no LLM, regex-first"** — The backlog was rewritten to reflect the decision to remove the LLM from the detection pipeline and lean on regex + Dutch wordlists + structure heuristics instead. Core redaction UX still comes first, then polish, then the SaaS layer. See "Guiding philosophy" below and `docs/reference/woo-redactietool-analyse.md` for the rationale.

## Guiding philosophy

**1. No LLM in the codebase.** Detection is regex + Deduce NER + Meertens/CBS wordlists + structure heuristics (e-mailheaders, handtekeningblokken, aanhef) + a rule-based public-official filter. The Ollama/Gemma layer was removed entirely in April 2026 — there is no dormant code in the tree. The value of the tool is the review workflow, not a smarter model. See `docs/reference/woo-redactietool-analyse.md` for the rationale and `docs/reference/llm-revival.md` for the constraints on any future revival.

**2. Core functionality first.** The prototype has to feel great at the one thing it does: helping a Woo reviewer redact a document. Manual text selection, area selection, undo, search-and-redact, and page completeness are done. The next detection work is beefing up the rule-based layer (todos #12–#16) and the UX that leans on it (#17, #19, #20, #21) — this is what compensates for removing the LLM.

**3. Then polish.** Loading states, animations, and mobile responsiveness come right after core editing. The demo has to look and feel great, not just work.

**4. Only then, the SaaS layer.** Authentication, organizations, roles, billing, analytics, deployment hardening — all deferred until the core experience is compelling. Today the app is single-document and runs locally; that's fine for a prototype and for pilot demos.

**5. Distribution = open core + generous free tier.** Hosting cost is essentially zero (no LLM, no document storage), so we can afford a free tier that is *the marketing engine*, not a teaser. The model:

- **Self-host (free, MIT)** for IT-savvy gemeenten and ministries that want full data sovereignty (#43).
- **Hosted Gratis tier** for individual reviewers — no signup wall on `/try`, full export, no watermark, no document cap. The trust unlock is "uw PDF verlaat nooit uw browser"; we do not undermine it with friction.
- **Hosted Team tier (~€79–€99/month per organization)** sells the things self-hosting and the Gratis tier *don't* give you: multi-user, shared custom wordlists (#21), audit log (#19), SSO (#42), priority support, NL-hosted with DPA.
- **Hosted Enterprise** for provincies and ministries — custom pricing, SLA, ISO27001/NEN7510 paperwork, training.

Pricing principles: don't gate the core review loop, don't anchor low (€99 reads as professional, €19 as hobby), per-org flat not per-document, free tier is the marketing. See #37 for the full ladder and rationale, and #43 for the open-source release prep.

**6. Privacy-first: client-side wherever possible, ephemeral on the server where unavoidable.** This project is being built for Dutch government users handling privacy-sensitive documents. The trust story is deliberately one sentence: *uw documenten verlaten nooit uw infrastructuur en er komt geen taalmodel aan te pas.*

- **PDFs never leave the browser** (except for ephemeral, in-memory redaction during export).
- **Extracted text** is sent to the server only for detection (Deduce NER + rules). The server processes it in memory and discards it — nothing is logged, nothing is persisted.
- **The database stores decisions, not content.** Bbox coordinates, article references, review status — no `entity_text`, no document bodies, no export artifacts.
- **No LLM in the live pipeline.** No GPU, no model hosting, no verwerkersovereenkomst for an external model provider. Phase 2 (browser-only LLM via WebGPU) is a possibility for later, not a current dependency.
- **We accept limitations this imposes.** Draft-saving, cross-session resume, and server-side previews are harder (or impossible) under this model. That is a deliberate trade-off. When a feature seems to require server-side document storage, the right answer is usually "keep it in IndexedDB" or "drop the feature" — not "compromise the privacy story."

Full architectural specification: [#00 — Client-first architecture](done/00-client-first-architecture.md). Pivot rationale: [`docs/reference/woo-redactietool-analyse.md`](../reference/woo-redactietool-analyse.md). The pivot itself: [`done/35-deactivate-llm.md`](done/35-deactivate-llm.md).

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
| 35 | ~~[Deactivate LLM layer (dormant)](done/35-deactivate-llm.md)~~ | P0 | S | Pivot 2026-04 |

## Phase B — Core Redaction Experience (the prototype's reason for existing)

This phase turns the viewer into an actual editing tool and beefs up the rule-based detection that replaces the removed LLM. **Everything here must respect the client-first architecture** — manual detections live in IndexedDB first; server metadata sync is secondary and can be stubbed/deferred if it slows us down. Detection work (#12–#16) closes the gap left by `35-deactivate-llm.md`; UX work (#15, #17) makes the review loop fast enough that losing 10–15% detection accuracy doesn't matter. Numbering reflects priority: the lowest available numbers are the pivot's most urgent work.

| # | Todo | Priority | Size | Source |
|---|------|----------|------|--------|
| 5 | ~~[Review/Edit mode toggle](done/05-mode-toggle.md)~~ | P1 | M | Editing |
| 6 | ~~[Manual text selection redaction](done/06-manual-text-redaction.md)~~ | P1 | L | Editing |
| 7 | ~~[Area selection redaction](done/07-area-selection.md)~~ | P1 | M | Editing |
| 8 | ~~[Undo/redo](done/08-undo-redo.md)~~ | P1 | M | Editing |
| 9 | ~~[Search-and-redact](done/09-search-and-redact.md)~~ | P1 | L | Editing |
| 10 | ~~[Page completeness review](done/10-page-completeness.md)~~ | P1 | M | Editing |
| 11 | ~~[Boundary adjustment](done/11-boundary-adjustment.md)~~ | P2 | L | Editing |
| 12 | ~~[Name lists: Meertens voornamen + CBS achternamen](done/12-name-lists-meertens-cbs.md)~~ | P1 | M | Pivot 2026-04 |
| 13 | ~~[Functietitel + publiek-functionaris rule engine](done/13-functietitel-publiek-functionaris.md)~~ | P1 | M | Pivot 2026-04 |
| 14 | ~~[Structuurherkenning (headers, signatures, aanhef)](done/14-structuurherkenning.md)~~ | P1 | M | Pivot 2026-04 |
| 15 | ~~[Tier 2 suggestion card UX](done/15-tier2-suggestion-ux.md)~~ | P1 | M | Reviewer feedback 2026-04 |
| 16 | ~~[Tier 1 gaps: KvK, BTW, geboortedatum](done/16-tier1-gaps.md)~~ | P2 | S | Pivot 2026-04 |
| 17 | ~~[Publieke functionarissen referentielijst (per-document)](done/17-publieke-functionarissen-referentielijst.md)~~ | P2 | M | Pivot 2026-04 |
| 18 | ~~[Split and merge detections](done/18-split-merge.md)~~ | P3 | M | Editing |
| 48 | ~~[Non-Dutch surname coverage for Tier 2 persoon](done/48-non-dutch-surnames.md)~~ | P2 | M | Bug surfaced 2026-04 |

## Phase C — Polish & launch-ready (the "can we ship this to the public?" phase)

Once the core loop works, make it feel great **and** get it in front of real users. This phase absorbs the polish work *and* the marketing/infra items that used to live in the old "SaaS Launch" phase, because the GTM plan is to launch **without auth or billing** and validate demand first. See the "GTM & launch sequencing" section below for the rationale.

**Audit trail moved up** — the analyse.md identifies "onderbouwing per gelakte passage, exporteerbaar naar het Woo-besluit" as the headline sales feature, so the redaction log is P1 here (already done).

| # | Todo | Priority | Size | Source |
|---|------|----------|------|--------|
| 19 | ~~[Redaction log & audit trail](done/19-redaction-log.md)~~ | P1 | L | Draft Workflow + Pivot 2026-04 |
| 20 | ~~[Bulk sweep flows (header block, signature block, same-name)](done/20-bulk-sweep-flows.md)~~ | P2 | M | Pivot 2026-04 |
| 21 | ~~[Per-document custom wordlist](done/21-per-document-custom-wordlist.md)~~ | P2 | S | Pivot 2026-04 |
| 22 | ~~[Loading states & skeletons](done/22-loading-states.md)~~ | P2 | M | Testing & Polish |
| 23 | ~~[Landing page animations](done/23-animations.md)~~ | P3 | S | Testing & Polish |
| 24 | ~~[Mobile responsive polish](done/24-mobile-responsive.md)~~ | P3 | S | Testing & Polish |
| 39 | [Deployment setup](39-deployment.md) | P1 | M | Testing & Polish |
| 40 | [Legal pages & SEO](40-legal-seo.md) | P1 | S | Testing & Polish |
| 41 | [Analytics (Plausible)](41-analytics.md) | P1 | S | Testing & Polish |
| 43 | [Open source release & self-host](43-open-source-release.md) | P1 | M | Distribution strategy 2026-04 |
| 44 | ~~[Sample documents on landing page](done/44-sample-documents-landing.md)~~ | P1 | S | Distribution strategy 2026-04 |
| 45 | ~~[Lead capture email form](done/45-lead-capture.md)~~ | P1 | S | GTM plan 2026-04 |
| 46 | [Convert-to-PDF ingestion (docx, odt, xlsx, images, zip)](46-convert-to-pdf-ingestion.md) | P1 | L | Multi-format support 2026-04 |
| 47 | [Email / .msg thread ingestion](47-email-msg-ingestion.md) | P1 | M | Multi-format support 2026-04 |
| 48 | [Accessible PDF export (lang tag, XMP, alt text, PDF/A-2b)](48-accessible-pdf-export.md) | P1 | M | Accessibility plan 2026-04 |

Launch when all P1s in this phase are green. That is the "Phase D milestone" below.

## Phase D — Public launch & market validation (milestone, not a work item)

No new todos — this is the "ship it, drive traffic, measure" checkpoint. Expected activities:

- Deploy to production URL
- Soft launch via personal network (ex-colleagues in gemeenten, privacy/BOFH-style blogs, LinkedIn)
- Measure in Plausible: `/try` starts, sample opens, exports completed, email signups
- Collect qualitative feedback through the email list and any direct outreach
- **Decision gate:** is there enough signal — repeat users, team-lead inquiries, "my colleagues need this too" — to justify building multi-user features? If yes → Phase E. If no → iterate on detection quality, UX, samples, and marketing until there is signal, or kill the project.

**Do not start Phase E before this gate.** Building auth + orgs speculatively is the single biggest way to waste weeks on this project.

## Phase E — Team features (only once a team lead asks)

Triggered by the Phase D decision gate. The ordering here reflects the real dependency graph (auth → orgs → roles → members). **#33 (Organizations) was written against the old multi-document shape and needs a rewrite before implementation** — the app is currently single-document; see `CLAUDE.md`.

| # | Todo | Priority | Size | Source |
|---|------|----------|------|--------|
| 32 | [Authentication (Better Auth)](32-authentication.md) | P0 (once triggered) | L | Auth & Billing |
| 33 | [Organizations & data scoping](33-organizations.md) | P0 (once triggered) | L | Auth & Billing |
| 34 | [Roles & permissions](34-roles-permissions.md) | P1 | M | Auth & Billing |
| 36 | [Member management & invitations](36-member-management.md) | P1 | M | Auth & Billing |

## Phase F — Draft workflow & export enhancements (for paying team pilots)

Everything in this phase presupposes a multi-user model: approval gates, jurist comments, re-export audit trails. Solo users on a single-doc prototype do not need any of this — they just export when ready. Do not build any of it before Phase E is done AND a team pilot is asking for it. If you catch yourself planning this phase before that signal exists, stop.

Concept export (#29) is the one arguable exception: the watermark prevents accidental publication and could sneak into Phase C if a pilot reviewer asks for it. Leave it here by default.

| # | Todo | Priority | Size | Source |
|---|------|----------|------|--------|
| 25 | [Document lifecycle (draft/approve)](25-document-lifecycle.md) | P2 (post-signal) | M | Draft Workflow |
| 26 | [Draft preview & side-by-side](26-draft-preview.md) | P2 | M | Draft Workflow |
| 27 | [Draft comments](27-draft-comments.md) | P3 | M | Draft Workflow |
| 28 | [Export versioning & re-export](28-export-versioning.md) | P2 | M | Draft Workflow |
| 29 | [Concept export with watermark](29-concept-export.md) | P3 | S | Draft Workflow |
| 30 | [Redaction map generation](30-redaction-map.md) | P3 | M | Draft Workflow |
| 31 | [Redaction inventory (CSV/XLSX)](31-redaction-inventory.md) | P3 | S | Draft Workflow |

## Phase G — Monetization (only after 1–3 manual-invoice pilots)

Don't integrate a payment processor before someone says "take my money." A manual invoice for the first 1–3 team customers is fine, teaches you more than Mollie does about the deal shape, and lets you ship Mollie with real contract knowledge instead of guesses.

| # | Todo | Priority | Size | Source |
|---|------|----------|------|--------|
| 37 | [Mollie billing integration](37-mollie-billing.md) | P2 (post-pilots) | XL | Auth & Billing |
| 38 | [Email service (transactional)](38-email-service.md) | P2 | M | Testing & Polish |
| 42 | [Microsoft SSO & 2FA](42-sso-2fa.md) | P3 (sales-driven) | M | Auth & Billing |

---

## GTM & launch sequencing (2026-04)

The backlog used to be phased "core → polish → draft workflow → export → auth → SaaS launch," which implicitly assumed you'd build auth and multi-tenancy *before* shipping to users. That ordering is wrong for this project for three reasons:

1. **Client-first means there's nothing for an account to persist.** No documents, no saved drafts, no cross-session state. An account in v1 would be a hollow shell. Every hour spent on auth is an hour not spent on detection quality, samples, or marketing.
2. **Draft workflow is inherently multi-user.** Approve/reopen/comment only make sense when a second person exists. Without auth, those features are theater.
3. **The cheapest way to validate demand is to ship the individual-reviewer experience and measure.** Email capture gives us the same "who's interested" signal as a login wall, without the engineering cost or the conversion friction.

So the new order is: finish polish + launch infra (Phase C), ship publicly and measure (Phase D), build team features only if the signal is there (Phase E), build draft/export compliance features only for paying pilots (Phase F), integrate billing only after manual invoices have taught us the contract shape (Phase G).

**Conversion without auth.** The lead capture (#45) is how we avoid losing interested users. When someone finishes an export or lingers on the landing page, we offer a "blijf op de hoogte / vraag een teamdemo aan" email form. Those emails become the invite list the day team features exist. No one is lost by deferring auth.

---

## Briefings Not Adopted (or deferred)

Some briefing suggestions are **deferred or modified**:

- **Tier 3 LLM content analysis** (main briefing) — Removed from the live pipeline in April 2026 (see `done/35-deactivate-llm.md` and `docs/reference/woo-redactietool-analyse.md`). The Ollama provider stays in-tree as a dormant revival path. The detection gap is closed by rule-based todos #12–#17. Tier 3 is "reserved" in the data model but has no active caller.
- **Tier 2 LLM person-role classification** (main briefing) — Same deactivation. Replaced by a rule-based public-official detector (#13) and structure heuristics (#14). Reviewers now confirm/reject more pending cards, but the UX work in #15 and #20 keeps the review loop fast.
- **Ollama + Gemma setup** (WOO_BUDDY_TODO.md) — The personal setup list describing Ollama installation has moved to `done/WOO_BUDDY_TODO.md` as historical reference for the dormant revival path. No longer required for running the application.
- **Server-side PDF storage** (all briefings) — Replaced by client-first architecture (#00). PDFs never persist on the server.
- **MinIO as document store** (main briefing) — Removed or reduced to optional temporary artifact storage. See #00.
- **`entity_text` in database** (all briefings) — Detection records store positions and types, not the actual sensitive text. See #00.
- **Subscription tier pricing** (Auth & Billing) — The specific price points (49/149/349) are business decisions, not engineering tasks. Captured in the billing todo as configurable, not hardcoded.
- **Celery job queue** (Draft Workflow) — Overkill for MVP. Background tasks via FastAPI's built-in `BackgroundTasks` suffice until proven otherwise.
- **Full fuzzy name matching** (Editing) — Simplified to basic normalization for Phase B. Full Dutch name-particle matching is a P3 enhancement.
- **Self-hosted version** (Auth & Billing) — ~~Briefing correctly says "should not complicate the architecture now." Agreed, not tracked.~~ **Reversed 2026-04.** Self-hosting is now a strategic pillar: it kills the "we can't put data in the cloud" procurement objection for government IT, makes the privacy-first claim auditable, and is essentially free to support because the architecture is already client-first with no GPU/LLM dependency. Tracked as #43.
- **Watermarked or preview-only trial** (considered 2026-04) — Rejected. Civil servants need to feel the full review loop on a real document or they bounce, and crippling the trial undermines the "PDF never leaves your browser" trust message that is our strongest asset. The trial is the marketing — see #37 pricing model and #44 sample documents.
- **Per-document or "3 docs/month" free tier cap** (earlier version of #37) — Rejected. Hosting is essentially free, so rationing the core loop costs more conversions than it saves on infra. Billing gates team features (invites, shared wordlists, audit log, SSO), not the review loop.

## How to Use This Backlog

1. Pick the current phase (A → B → C → ...)
2. Work through todos within the phase in order
3. A todo is "done" when its acceptance criteria are met — then move the file to `done/` and update this index
4. Cross-phase dependencies are noted — respect them
5. P3 items within a phase can be skipped and revisited later
6. **Every todo must respect the client-first architecture in #00** — if a feature seems to require server-side document storage, the design is wrong; revisit before implementing
