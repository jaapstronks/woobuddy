# 37 — Mollie Billing Integration

- **Priority:** P2
- **Size:** XL (1–2 weeks)
- **Source:** Auth & Billing briefing, "Payments: Mollie" section
- **Depends on:** #32 (Auth), #33 (Organizations)
- **Blocks:** Nothing (features work without billing, billing adds limits)

## Why

For WOO Buddy to be a sustainable SaaS product, it needs a revenue model. Mollie is the right payment provider for a Dutch government tool: European, GDPR-native, supports iDEAL (dominant NL payment method), familiar to government organizations.

## Pricing model (2026-04 strategy)

Hosting cost is essentially zero (no LLM, no document storage), so the free tier can be *generous* and serve as the marketing engine. Revenue comes from team features and enterprise paperwork — not from rationing the core review loop.

**Tier ladder:**

| Tier | Audience | Price | Includes |
|------|----------|-------|----------|
| **Self-host** | IT-savvy gemeenten, ministries with strict data sovereignty | Free, MIT-licensed | Everything. Run it on your own infrastructure. See #43. |
| **Gratis (hosted)** | Individual reviewers trying it out | €0, no signup | Unlimited single-user use, full export, no watermark, no document cap. Rate-limited by IP only if abuse appears. |
| **Team** | A municipality's Woo team | ~€79–€99/month per organization | Multi-user, shared custom wordlists (#21), audit log (#19), SSO (#42), priority support, NL-hosted with DPA |
| **Enterprise** | Provincies, ministries, large gemeenten | Custom (~€500–€2000/month) | Dedicated instance, SLA, ISO27001/NEN7510 paperwork, training, on-site onboarding |

**Pricing principles:**
- **Don't gate the core review loop.** No "3 documents/month" cap, no watermarks, no preview-only mode. The trial must let a reviewer feel the full workflow on a real document, or the bottoms-up motion dies. (Earlier versions of this doc proposed a 3-doc cap — explicitly rejected.)
- **Don't anchor low.** €19/month reads as hobby project; €99/month reads as professional software a gemeente can expense. Free → €99 is a healthier ladder than free → €19.
- **Per-org flat, not per-document.** Civil servants can't forecast volume and won't expense usage-based billing.
- **Free tier is the marketing.** No watermarks, no signup wall on `/try`. The "your PDF never leaves your browser" message is the trust unlock; do not undermine it with friction.
- Keep prices configurable, not hardcoded.

## Scope

### Backend (`backend/app/billing/`)

- [ ] `mollie_client.py` — Mollie SDK initialization
- [ ] `customers.py` — create/manage Mollie customers (one per organization)
- [ ] `subscriptions.py` — create/update/cancel subscriptions
- [ ] `webhooks.py` — handle Mollie webhook callbacks (publicly accessible, not authenticated)
- [ ] `plans.py` — plan definitions with configurable limits (users, documents/month, features)
- [ ] `middleware.py` — request middleware to check plan limits on document/dossier creation

### Database tables

- [ ] `mollie_customers` — org ↔ Mollie customer mapping
- [ ] `subscriptions` — plan, status, period tracking
- [ ] `payments` — payment history
- [ ] `usage` — monthly analysis/export counters per org (counts API calls, not stored documents)

### Payment flows

- [ ] First payment: create Mollie customer → first payment with `sequenceType: "first"` → redirect to checkout → webhook → create subscription
- [ ] Recurring: Mollie charges automatically → webhook updates status
- [ ] Failed payment: 7-day grace period → downgrade to Gratis → existing dossiers read-only
- [ ] Webhook security: on webhook receipt, call Mollie API to verify payment status (Mollie's recommended model)

### Frontend (`/app/org/billing`)

- [ ] Current plan with features and limits
- [ ] Usage this month (documents uploaded/remaining)
- [ ] Plan comparison table with upgrade/downgrade buttons
- [ ] Payment history
- [ ] Friendly limit-exceeded message with upgrade path

### Plan enforcement (adapted for client-first + generous-free-tier strategy)

- [ ] **Do not gate `/api/analyze` for the Gratis tier.** Anonymous and Gratis users get full analysis. Enforcement is on team features (user invites, shared wordlists, audit log access), not on the review loop.
- [ ] On user invite: check seat limit per team
- [ ] On shared-wordlist write / audit-log read / SSO config: gate by Team plan
- [ ] Return `402 Payment Required` with a clear Dutch message and upgrade link only on team-feature endpoints
- [ ] Optional: per-IP rate limit on `/api/analyze` (e.g. 60/hour) as abuse protection — not as a paywall

### API endpoints

- [ ] `POST /api/billing/checkout` — create first payment, return checkout URL
- [ ] `POST /api/billing/upgrade` — change plan
- [ ] `POST /api/billing/cancel` — cancel subscription
- [ ] `GET /api/billing/subscription` — current subscription
- [ ] `GET /api/billing/payments` — payment history
- [ ] `GET /api/billing/usage` — current period usage
- [ ] `POST /api/billing/webhook` — Mollie webhook (public, unauthenticated)

## Acceptance Criteria

- Organization can upgrade from Gratis to Team via Mollie checkout
- Recurring payments work via Mollie subscriptions
- **Anonymous and Gratis users can analyze and export documents without limit** — billing only enforces team features
- Team-feature endpoints (invite, shared wordlists, audit log) return `402` for Gratis orgs with a clear upgrade message
- Failed payment triggers grace period and eventual downgrade to Gratis (team features lock; review loop keeps working)
- Billing page shows plan, usage (informational, not a cap), and payment history

## Not in Scope

- Custom enterprise pricing
- Annual billing discounts
- VAT handling (Mollie handles this)
- Invoicing (Mollie provides receipts)
