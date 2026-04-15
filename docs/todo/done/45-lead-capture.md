# 45 — Lead Capture Email Form

- **Priority:** P1
- **Size:** S (< 1 day)
- **Source:** GTM plan 2026-04 (see README "GTM & launch sequencing")
- **Depends on:** Nothing
- **Blocks:** Phase D public launch
- **Status (2026-04-15):** Implemented. Backend pushes contacts directly
  into Brevo list 4 ("Woobuddy") — no Postgres persistence, no CSV export,
  no double opt-in. DNS for `hoi@woobuddy.nl` wired up on TransIP via API.
  See "Deployment wiring (as built)" below.

## Deployment wiring (as built)

The original scope stored leads in Postgres with a CSV admin export. The
as-built version bypasses that entirely and uses Brevo as the system of
record for the audience list. Hosting cost stays zero (Brevo free tier
covers tens of thousands of contacts) and there's no CSV to babysit.

### Brevo

- **List:** "Woobuddy", ID `4`. Configured via `BREVO_LIST_ID` (default 4).
- **API key:** `BREVO_API_KEY` env var. The key has an IP allowlist on
  the Brevo side — every deployment environment (local dev, staging,
  production) needs its outbound IP added in **Brevo → Security →
  Authorised IPs**, or the restriction removed on that key. Missing IPs
  surface in backend logs as `leads.brevo_auth_error` and the form shows
  a generic retry message.
- **Contact attributes sent:** `SOURCE` (`landing` or `post-export`),
  `FIRSTNAME` (the form's `name`), `COMPANY` (the form's
  `organization`), `MESSAGE`. `SOURCE` and `MESSAGE` are custom
  attributes the Brevo account owner should create in the dashboard; if
  they don't exist yet, Brevo silently drops them and the contact is
  still created.
- **Welcome email:** handled by a Brevo automation on list-add for list
  4 — no transactional send from our backend. To wire it up:
  1. **Senders, Domains & Dedicated IPs → Senders** → add
     `hoi@woobuddy.nl` (can only be saved once DNS is validated, see
     below).
  2. **Campaigns → Templates** → create a transactional template
     "WOO Buddy — welkom" with the welcome copy. Set the sender to
     `WOO Buddy <hoi@woobuddy.nl>`.
  3. **Automations → New automation → Workflow from scratch** → trigger
     "Contact added to a list" → select list 4 → action "Send an email"
     → pick the welkom template. Activate.
- **Duplicate behavior:** contacts POST with `updateEnabled: true`, so a
  second signup from the same address updates attributes rather than
  failing. Belt-and-braces: if Brevo still returns `duplicate_parameter`
  the backend treats it as a silent success so the form can never
  reveal list membership.

### DNS (TransIP, woobuddy.nl)

Added via TransIP v6 API (`TRANSIP_ACCESS_TOKEN` in env, label
`woobuddy`). Four records touched:

| Change | Name | Type | Content |
|---|---|---|---|
| ADD | `@` | TXT | `brevo-code:93f3963c91ea8662526f324f83d4217d` |
| ADD | `brevo1._domainkey` | CNAME | `b1.woobuddy-nl.dkim.brevo.com.` |
| ADD | `brevo2._domainkey` | CNAME | `b2.woobuddy-nl.dkim.brevo.com.` |
| REPLACE | `_dmarc` | TXT | `v=DMARC1; p=none;` → `v=DMARC1; p=none; rua=mailto:rua@dmarc.brevo.com` |

Left untouched: the existing neutral SPF (`v=spf1 ~all`, Brevo uses
DKIM-only auth so it didn't ask for one), TransIP's own DKIM selectors
(`transip-A/B/C._domainkey`), and A/AAAA/MX/www.

**MX caveat:** `woobuddy.nl` currently has `MX 10 @` — nothing catches
inbound mail. Outbound from `hoi@woobuddy.nl` via Brevo works, but
replies to that address bounce. Set up a forwarder (ImprovMX, Fastmail,
whatever) before going live.

### Environment variables summary

```
BREVO_API_KEY=...                 # from Brevo SMTP & API settings
BREVO_LIST_ID=4                   # default matches list "Woobuddy"
TRANSIP_ACCESS_TOKEN=...          # only needed for DNS automation, not at runtime
```

## Why

The GTM plan launches WOO Buddy publicly **without auth**. Under client-first there is nothing for an account to persist — no documents, no saved drafts, no cross-session state — so building auth before launch would be an expensive shell. But we still need a way to convert interested users into a reachable audience, otherwise every visitor who thinks "this is cool, I'll check back when they have team features" is silently lost.

Lead capture is the lightweight substitute for registration. A single email field, optional name and organization, one line of consent copy, and a `POST /api/leads` that stores the row in Postgres and optionally forwards to an email address. When team features eventually ship, this list becomes the invite audience.

This is the **last piece** needed before Phase D (public launch). Ship it last so the CTA copy can reference whichever polish items land at the same time (sample documents, legal pages, open-source release).

## Scope

### Frontend component

- [ ] `<LeadCaptureForm>` Svelte component in `frontend/src/lib/components/marketing/`
  - Fields: `email` (required), `name` (optional), `organization` (optional), `message` (optional textarea, small)
  - Consent checkbox: "Ik wil op de hoogte blijven van updates en teamfuncties. WOO Buddy mag mij hiervoor mailen." Required.
  - Submit button: "Aanmelden"
  - States: idle, submitting, success, error. Success shows a short Dutch thank-you inline — no redirect, no modal.
  - Shoelace components: `sl-input`, `sl-textarea`, `sl-checkbox`, `sl-button`, `sl-alert` for errors. Follow the `onsl-input` pattern in `CLAUDE.md`.
  - Accessible: labels, error announcements via `aria-live`, keyboard-submittable.

### Placement

- [ ] **Landing page:** add a new `<StayInTheLoop>` section between `OpenSource` and `Footer` — headline "Blijf op de hoogte" + one paragraph + the form. Dutch copy should mention: solo-tier blijft gratis, teamfuncties in aantocht, geen spam.
- [ ] **Review screen post-export moment:** after the user successfully exports their redacted PDF, surface the same form inline in the export success state (or in a dismissible card below it). Copy: "Fijn dat je WOO Buddy hebt geprobeerd. Wil je gemaild worden als er teamfuncties zijn?"
- [ ] Both placements use the same component; only the `source` prop differs (`"landing"` / `"post-export"`).

### Backend

- [ ] New table `leads` (Alembic migration) with columns:
  - `id` (uuid, pk)
  - `email` (text, indexed, not null)
  - `name` (text, nullable)
  - `organization` (text, nullable)
  - `message` (text, nullable)
  - `source` (text, not null — e.g. `landing`, `post-export`)
  - `user_agent` (text, nullable — for anti-spam debugging, not fingerprinting)
  - `created_at` (timestamptz, default now, not null)
  - Unique index on `(lower(email), source)` so re-submits from the same place don't duplicate.
- [ ] `POST /api/leads` endpoint in `backend/app/api/leads.py`
  - Pydantic request model with email validation
  - Rate-limited by IP (simple in-memory bucket is fine for MVP — revisit if abused)
  - Returns `{ok: true}` on both new insert and duplicate (so the frontend doesn't reveal whether an address is already on the list)
  - **Does not log request bodies** (per client-first logging rule)
- [ ] `GET /api/admin/leads` — simple read endpoint gated by a shared admin token from env (`ADMIN_TOKEN`), returns CSV. No UI for this yet; use `curl` + header for now. (Proper admin UI is a later todo.)

### Copy (Dutch)

The landing section text (to be refined with the rest of the landing copy):

> **Blijf op de hoogte**
>
> WOO Buddy blijft gratis voor individuele Woo-reviewers. Er komen teamfuncties aan — gedeelde woordenlijsten, audit log, multi-user review. Laat je e-mail achter als je het wilt weten wanneer het zover is. Geen spam, geen tracking, geen nieuwsbrief waar je niet meer uit kunt.

The post-export variant is shorter:

> Fijn dat je WOO Buddy hebt geprobeerd. Wil je gemaild worden zodra er teamfuncties zijn?

## Acceptance Criteria

- Submitting a valid email stores a row in `leads` and shows an inline success state
- Duplicate submission is silently idempotent
- Consent checkbox is required and explicit
- Form is present on the landing page and on the post-export success screen
- `GET /api/admin/leads` with the admin token returns CSV; without the token it returns 401
- No document text or detection content appears in any request body or server log for this endpoint

## Not in Scope

- Mailchimp / Buttondown / ESP integration — Postgres + manual CSV export is fine for v1. Swap later if volume justifies it.
- Double opt-in email confirmation — GDPR-compliant for this kind of product-update list because consent is explicit and the list is low-volume. Revisit if we ever send marketing blasts.
- An in-app admin UI for browsing leads (`GET /api/admin/leads` CSV is enough)
- Unsubscribe management — handled manually until volume justifies building it
- Tracking or fingerprinting of any kind
