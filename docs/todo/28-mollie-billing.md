# 25 — Mollie Billing Integration

- **Priority:** P2
- **Size:** XL (1–2 weeks)
- **Source:** Auth & Billing briefing, "Payments: Mollie" section
- **Depends on:** #24 (Auth), #25 (Organizations)
- **Blocks:** Nothing (features work without billing, billing adds limits)

## Why

For WOO Buddy to be a sustainable SaaS product, it needs a revenue model. Mollie is the right payment provider for a Dutch government tool: European, GDPR-native, supports iDEAL (dominant NL payment method), familiar to government organizations.

## Assessment

The briefing's architecture is sound: Mollie integration in FastAPI (best Python SDK), subscription tiers per organization, webhook-based payment tracking. The specific price points (49/149/349) are business decisions — implement the tier system as configurable, not hardcoded.

**Adopt the architecture. Make pricing configurable.** Also: the Gratis tier at "3 documents/month" is smart — genuinely useful, not just a teaser.

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

### Plan enforcement (adapted for client-first)

- [ ] On analysis request (`/api/analyze`): check monthly analysis limit (replaces "document upload" limit since PDFs aren't uploaded)
- [ ] On user invite: check user limit
- [ ] On Tier 3 request: check if plan includes LLM analysis
- [ ] Return `402 Payment Required` with clear Dutch message and upgrade link
- [ ] Usage tracking counts analysis requests, not file uploads (since files stay in the browser)

### API endpoints

- [ ] `POST /api/billing/checkout` — create first payment, return checkout URL
- [ ] `POST /api/billing/upgrade` — change plan
- [ ] `POST /api/billing/cancel` — cancel subscription
- [ ] `GET /api/billing/subscription` — current subscription
- [ ] `GET /api/billing/payments` — payment history
- [ ] `GET /api/billing/usage` — current period usage
- [ ] `POST /api/billing/webhook` — Mollie webhook (public, unauthenticated)

## Acceptance Criteria

- Organization can upgrade from Gratis to a paid plan via Mollie checkout
- Recurring payments work via Mollie subscriptions
- Plan limits are enforced on document upload and user invites
- Failed payment triggers grace period and eventual downgrade
- Billing page shows plan, usage, and payment history

## Not in Scope

- Custom enterprise pricing
- Annual billing discounts
- VAT handling (Mollie handles this)
- Invoicing (Mollie provides receipts)
