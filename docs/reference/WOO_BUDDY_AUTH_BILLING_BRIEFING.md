# WOO Buddy — Supplementary Briefing: Auth, Users, Organizations & Payments

## Strategic Direction

WOO Buddy is a **SaaS product**. A gemeente-ambtenaar visits woobuddy.nl, creates an account, and starts working. No Docker, no self-hosting, no IT department involvement required. The codebase is open-source for transparency and trust — government users can inspect how their documents are processed — but the product is a hosted service.

A self-installable version may come later. It should not complicate the architecture now.

---

## What's Missing in the Current Briefings

The existing briefings have no user model. Specifically:

- `reviewed_by` and `actor` fields are free-text strings, not references to real users
- Dossiers are owned by nobody — anyone who has the URL could theoretically see them
- Multi-user workflows (reviewer, jurist, supervisor) are described but have no roles or permissions
- "Assign to a different reviewer" has no user list to assign to
- Draft comments have an "author" with no identity behind it
- There are no sessions, no login, no signup
- There is no concept of an organization (gemeente, provincie) that groups users and dossiers
- There is no billing — no way to charge for the service

This briefing fills all of these gaps.

---

## Authentication: Better Auth

### Why Better Auth

**Better Auth** is an open-source TypeScript authentication framework with first-class SvelteKit support. It stores all user data in your own PostgreSQL database — no external auth service, no data leaving your infrastructure.

Key reasons for choosing it:

- First-class SvelteKit + Svelte 5 integration (server hooks, runes-compatible client store)
- All auth tables live in the **same PostgreSQL database** as the rest of WOO Buddy — one database, one backup, one migration system
- Built-in **organization plugin** with roles, invitations, and member management
- Built-in **SSO plugin** with OIDC and SAML support — future-proofs for enterprise municipalities that want to connect their Azure AD or KeyCloak
- Email/password + social login (Microsoft is important — many government employees use Microsoft accounts)
- 2FA and passkey support (important for government trust)
- MIT licensed, actively maintained, large community

**Why not Auth.js?** No organization plugin, harder to extend.
**Why not Lucia?** Deprecated by its creator — now a learning resource, not an active library.
**Why not Clerk/Auth0?** External dependencies. User data leaves your control. Hard to justify for a government tool processing privacy-sensitive documents.

### What Better Auth provides

Better Auth creates and manages these tables in your PostgreSQL database:

- **`user`** — id, name, email, emailVerified, image, createdAt, updatedAt
- **`session`** — id, userId, token, expiresAt, ipAddress, userAgent
- **`account`** — id, userId, provider, providerAccountId, tokens (for social/SSO logins)
- **`verification`** — id, identifier, value, expiresAt (for email verification, password reset)

With the **organization plugin** enabled:

- **`organization`** — id, name, slug, logo, metadata, createdAt
- **`member`** — id, userId, organizationId, role, createdAt
- **`invitation`** — id, email, organizationId, role, status, inviterId, expiresAt

With the **SSO plugin** enabled (future, for enterprise):

- **`ssoProvider`** — id, providerId, organizationId, issuer, domain, oidcConfig/samlConfig

### Better Auth setup in the codebase

**Server-side** (`src/lib/server/auth.ts`):

```ts
import { betterAuth } from "better-auth";
import { organization } from "better-auth/plugins";
import { Pool } from "pg";

export const auth = betterAuth({
  database: new Pool({ connectionString: process.env.DATABASE_URL }),
  emailAndPassword: { enabled: true },
  socialProviders: {
    microsoft: {
      clientId: process.env.MICROSOFT_CLIENT_ID!,
      clientSecret: process.env.MICROSOFT_CLIENT_SECRET!,
    },
  },
  plugins: [
    organization({
      allowUserToCreateOrganization: true,
      organizationLimit: 5,
      membershipLimit: 50,
    }),
  ],
});
```

**SvelteKit hook** (`src/hooks.server.ts`):

```ts
import { auth } from "$lib/server/auth";
import { svelteKitHandler } from "better-auth/svelte-kit";

export async function handle({ event, resolve }) {
  const session = await auth.api.getSession({
    headers: event.request.headers,
  });
  if (session) {
    event.locals.session = session.session;
    event.locals.user = session.user;
  }
  return svelteKitHandler({ event, resolve, auth });
}
```

**Client-side** (`src/lib/auth-client.ts`):

```ts
import { createAuthClient } from "better-auth/svelte";
import { organizationClient } from "better-auth/client/plugins";

export const authClient = createAuthClient({
  plugins: [organizationClient()],
});
```

### Auth flow between SvelteKit and FastAPI

Better Auth runs inside SvelteKit. The FastAPI backend needs to know who is making each request. The recommended approach:

**Session token forwarding via SvelteKit proxy.** All API calls from the browser go through SvelteKit server routes, which validate the session and forward to FastAPI with a trusted `X-User-Id` and `X-Organization-Id` header. FastAPI trusts these headers because they come from the internal SvelteKit server, not from the browser directly.

This means:

- The browser never talks to FastAPI directly — all requests go through SvelteKit
- SvelteKit validates the session on every request via Better Auth
- FastAPI receives the authenticated user ID and organization ID as headers
- FastAPI uses these IDs for all database operations (scoping queries, recording audit entries)
- No separate auth validation needed in FastAPI — it trusts the proxy

SvelteKit already supports this pattern natively via `+server.ts` route handlers that proxy to the backend.

---

## Organizations: How Users and Dossiers Relate

### The model

An **organization** in WOO Buddy represents a team or department within a government body. It could be "Gemeente Utrecht — Juridische Zaken" or simply "Gemeente Almere." Organizations are the ownership boundary for dossiers, documents, and all associated data.

```
Organization (gemeente/team)
├── Members (users with roles)
│   ├── owner (admin, manages billing and members)
│   ├── admin (manages members, can approve documents)
│   ├── reviewer (processes dossiers, makes redaction decisions)
│   └── viewer (read-only access, can view but not modify)
├── Dossiers
│   ├── Documents
│   │   ├── Detections
│   │   ├── Exports
│   │   └── Page reviews
│   ├── Public officials list
│   └── Audit log
└── Subscription (billing plan via Mollie)
```

### Roles and permissions

| Role | Create dossiers | Review detections | Approve documents | Manage members | Manage billing |
|------|----------------|-------------------|-------------------|----------------|----------------|
| **owner** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **admin** | ✓ | ✓ | ✓ | ✓ | — |
| **reviewer** | ✓ | ✓ | — | — | — |
| **viewer** | — | — (read-only) | — | — | — |

The **viewer** role is important for transparency workflows — a manager or communication staff member may need to see the redacted result without being able to change decisions.

Better Auth's organization plugin supports custom roles and permissions out of the box. Define these roles as:

```ts
organization({
  roles: {
    owner: { permissions: ["dossier.*", "member.*", "billing.*", "document.*"] },
    admin: { permissions: ["dossier.*", "member.invite", "member.remove", "document.*"] },
    reviewer: { permissions: ["dossier.create", "dossier.read", "document.*"] },
    viewer: { permissions: ["dossier.read", "document.read"] },
  },
})
```

### Multi-organization support

A user can belong to multiple organizations. A consultant who advises multiple municipalities can switch between organizations in the UI. Better Auth tracks the "active organization" on the session.

### Invitation flow

1. Organization owner/admin enters email address
2. Better Auth sends an invitation email
3. Recipient clicks the link → if they have an account, they're added to the organization; if not, they create an account first, then get added
4. New member appears in the organization's member list with the assigned role

---

## Payments: Mollie

### Why Mollie

Mollie is a Dutch/European payment provider. For a Dutch government SaaS product, this is the natural choice:

- Dutch company, European data processing, GDPR-native
- Supports iDEAL (the dominant payment method in NL), SEPA Direct Debit, credit cards, Bancontact
- Subscription/recurring payments via the Subscriptions API
- Simple, transparent pricing — pay per transaction, no monthly fees
- Excellent Python SDK (`mollie-api-python`) for the FastAPI backend
- Government organizations are familiar with Mollie

### Why not Stripe?

Better Auth has a Stripe plugin but no Mollie plugin. However, Stripe is American, and for a product that explicitly handles privacy-sensitive government documents, using a European payment provider is a meaningful trust signal. The Mollie integration will be custom-built in the FastAPI backend, which is fine — it's straightforward.

### How Mollie subscriptions work

Mollie's recurring payment model:

1. **First payment** — customer pays via iDEAL, credit card, or another method. Mollie creates a **mandate** (authorization to charge again). Set `sequenceType: "first"`.
2. **Recurring payments** — using the mandate, Mollie can charge the customer automatically. You can either:
   - Use the **Subscriptions API** to let Mollie handle the schedule (charge €X every month automatically)
   - Use **on-demand recurring payments** to charge when you decide (more control)

For WOO Buddy, the **Subscriptions API** is the right choice — simple, Mollie handles the schedule, webhook notifications for each payment.

### Subscription tiers

| Tier | Price | What you get |
|------|-------|-------------|
| **Gratis** (Free) | €0 | 1 user, 3 documents/month, 1 dossier, no Tier 3 analysis |
| **Basis** | €49/month | 5 users, 50 documents/month, unlimited dossiers, full Tier 1-3 |
| **Professional** | €149/month | 20 users, 200 documents/month, priority LLM processing, export with motivation report |
| **Organisatie** | €349/month | Unlimited users, unlimited documents, SSO integration, dedicated support, custom public officials list management |

Pricing is per organization, not per user. This matches how government budgets work — a team gets a budget line, not individual subscriptions.

*These are starting-point numbers. Adjust based on market feedback.*

### Mollie integration architecture

Mollie integration lives in the **FastAPI backend**, not in SvelteKit. This is because:

- Mollie's best SDK is Python (`mollie-api-python`)
- Webhook endpoints need to be reliable server-side handlers
- Subscription state needs to be checked on API requests (is this org on the free tier? have they exceeded their document limit?)

```
backend/app/
├── billing/
│   ├── __init__.py
│   ├── mollie_client.py          # Mollie SDK initialization
│   ├── customers.py              # Create/manage Mollie customers
│   ├── subscriptions.py          # Create/update/cancel subscriptions
│   ├── webhooks.py               # Handle Mollie webhook callbacks
│   ├── plans.py                  # Plan definitions and limits
│   └── middleware.py             # Request middleware: check plan limits
```

### Mollie integration flow

**Signup → first payment:**

1. User creates account (Better Auth in SvelteKit)
2. User creates an organization
3. Organization starts on the **Gratis** tier (no payment needed)
4. When user wants to upgrade: SvelteKit calls FastAPI → FastAPI creates a Mollie customer (if not exists) → creates a first payment with `sequenceType: "first"` → returns the `checkoutUrl`
5. SvelteKit redirects user to Mollie's hosted checkout (iDEAL, credit card, etc.)
6. User completes payment → Mollie redirects back to WOO Buddy
7. Mollie sends webhook → FastAPI processes it → creates a Mollie subscription for recurring billing → updates the organization's plan in the database

**Recurring billing:**

1. Mollie automatically charges the organization every month via the subscription
2. Mollie sends a webhook for each payment (successful, failed, etc.)
3. FastAPI processes the webhook → updates payment status in the database
4. If payment fails: Mollie does NOT retry automatically. After a configurable grace period (e.g., 7 days), the organization is downgraded to the Gratis tier. Existing dossiers are preserved (read-only), but new documents cannot be uploaded.

**Plan enforcement:**

On every API request that creates a document or dossier, the FastAPI middleware checks:
- Which plan is the organization on?
- How many documents have been uploaded this month?
- How many users does the organization have?
- Is the requested feature (e.g., Tier 3 analysis) included in the plan?

If the limit is exceeded, return a `402 Payment Required` with a clear message and a link to upgrade.

### Database tables for billing

```sql
-- Mollie customer mapping
CREATE TABLE mollie_customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organization(id) ON DELETE CASCADE,
    mollie_customer_id TEXT NOT NULL UNIQUE,  -- Mollie's cst_xxx ID
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Subscription tracking
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organization(id) ON DELETE CASCADE,
    mollie_subscription_id TEXT UNIQUE,       -- Mollie's sub_xxx ID
    plan TEXT NOT NULL DEFAULT 'gratis',      -- gratis, basis, professional, organisatie
    status TEXT NOT NULL DEFAULT 'active',    -- active, pending, canceled, past_due
    current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Payment history
CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organization(id),
    subscription_id UUID REFERENCES subscriptions(id),
    mollie_payment_id TEXT NOT NULL UNIQUE,   -- Mollie's tr_xxx ID
    amount_value TEXT NOT NULL,               -- "49.00"
    amount_currency TEXT NOT NULL DEFAULT 'EUR',
    status TEXT NOT NULL,                     -- paid, failed, expired, canceled
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Usage tracking (for plan limit enforcement)
CREATE TABLE usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organization(id) ON DELETE CASCADE,
    period_start DATE NOT NULL,              -- First day of the month
    documents_uploaded INTEGER DEFAULT 0,
    documents_processed INTEGER DEFAULT 0,
    llm_calls INTEGER DEFAULT 0,
    UNIQUE(organization_id, period_start)
);
```

---

## Revised Data Model: Everything Scoped to Organizations

Every existing table in the briefings needs an `organization_id` foreign key. This is the fundamental change. Nothing exists outside an organization.

### Changes to existing tables

- **`dossiers`** — add `organization_id UUID REFERENCES organization(id)`, add `created_by UUID REFERENCES user(id)`
- **`documents`** — already scoped via dossier → organization. Add `uploaded_by UUID REFERENCES user(id)`
- **`detections`** — add `reviewed_by UUID REFERENCES user(id)` (replace free-text string)
- **`audit_log`** — add `actor_id UUID REFERENCES user(id)` (replace free-text string), add `organization_id`
- **`public_officials`** — already has organization scope. Good as-is.
- **`draft_comments`** — add `author_id UUID REFERENCES user(id)` (replace free-text string)
- **`exports`** — add `created_by UUID REFERENCES user(id)`
- **`page_reviews`** — add `reviewer_id UUID REFERENCES user(id)`
- **`motivation_texts`** — add `edited_by UUID REFERENCES user(id)`

### User preferences

New table for per-user settings:

```sql
CREATE TABLE user_preferences (
    user_id UUID PRIMARY KEY REFERENCES user(id) ON DELETE CASCADE,
    default_organization_id UUID REFERENCES organization(id),
    keyboard_shortcuts_enabled BOOLEAN DEFAULT true,
    default_view TEXT DEFAULT 'review',        -- review, edit, draft
    items_per_page INTEGER DEFAULT 50,
    language TEXT DEFAULT 'nl',                -- nl, en (future)
    updated_at TIMESTAMPTZ DEFAULT now()
);
```

---

## Frontend: Auth Pages and Organization Management

### New routes

```
/auth/login                   Email/password login + Microsoft social login
/auth/signup                  Registration
/auth/verify                  Email verification
/auth/forgot-password         Password reset request
/auth/reset-password          Password reset form

/app/org                      Organization switcher (if user has multiple)
/app/org/settings             Organization settings (name, logo)
/app/org/members              Member management (invite, remove, change roles)
/app/org/billing              Subscription management, plan selection, payment history
/app/settings                 Personal settings (name, email, password, 2FA, preferences)
```

### Auth flow for new users

1. User visits woobuddy.nl → landing page
2. Clicks "Probeer gratis" or uploads a PDF
3. Prompted to create an account (email/password or Microsoft login)
4. After signup → email verification
5. Prompted to create an organization (name it after their team/municipality)
6. Redirected to `/app` — dashboard with their first (empty) dossier list
7. The `/try` quick-upload flow now works the same but requires login first. The temporary dossier is created inside their organization.

### Organization switcher

If a user belongs to multiple organizations, show a **switcher** in the app header. Clicking it shows a dropdown of organizations. Selecting one switches the active organization — all data in the app changes to that organization's dossiers, documents, members, etc.

Better Auth tracks the active organization on the session. The SvelteKit proxy passes the active `organization_id` to FastAPI on every request.

### Billing page (`/app/org/billing`)

Shows:
- Current plan with features and limits
- Usage this month (documents uploaded, documents remaining)
- Plan comparison table with upgrade/downgrade buttons
- Payment history (list of past payments with status)
- "Beheer abonnement" (Manage subscription) — for updating payment method or canceling

Upgrade flow:
1. User selects a plan → SvelteKit calls FastAPI
2. FastAPI creates a Mollie first payment (if no mandate exists) or immediately creates/updates the subscription
3. User is redirected to Mollie checkout if first payment is needed
4. After payment → webhook → subscription active → page refreshes to show new plan

---

## Environment Variables (additions)

```env
# Better Auth
BETTER_AUTH_SECRET=                     # openssl rand -base64 32
BETTER_AUTH_URL=https://woobuddy.nl

# Microsoft social login
MICROSOFT_CLIENT_ID=
MICROSOFT_CLIENT_SECRET=

# Mollie
MOLLIE_API_KEY=                        # test_xxx or live_xxx
MOLLIE_WEBHOOK_BASE_URL=https://woobuddy.nl  # Base URL for webhook callbacks

# Email (for verification, password reset, invitations)
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=noreply@woobuddy.nl
```

---

## Project Structure (additions)

```
frontend/src/
├── lib/
│   ├── server/
│   │   └── auth.ts                     Better Auth server config
│   ├── auth-client.ts                  Better Auth client
│   └── components/
│       ├── auth/
│       │   ├── LoginForm.svelte
│       │   ├── SignupForm.svelte
│       │   ├── ForgotPassword.svelte
│       │   ├── MicrosoftLoginButton.svelte
│       │   └── TwoFactorSetup.svelte
│       ├── org/
│       │   ├── OrgSwitcher.svelte
│       │   ├── OrgSettings.svelte
│       │   ├── MemberList.svelte
│       │   ├── InviteMember.svelte
│       │   └── RoleSelector.svelte
│       └── billing/
│           ├── PlanSelector.svelte
│           ├── PlanComparison.svelte
│           ├── UsageMeter.svelte
│           ├── PaymentHistory.svelte
│           └── BillingSettings.svelte
├── routes/
│   ├── auth/
│   │   ├── login/+page.svelte
│   │   ├── signup/+page.svelte
│   │   ├── verify/+page.svelte
│   │   ├── forgot-password/+page.svelte
│   │   └── reset-password/+page.svelte
│   └── app/
│       ├── org/
│       │   ├── settings/+page.svelte
│       │   ├── members/+page.svelte
│       │   └── billing/+page.svelte
│       └── settings/+page.svelte
└── hooks.server.ts                     Better Auth handler + session

backend/app/
├── billing/
│   ├── mollie_client.py
│   ├── customers.py
│   ├── subscriptions.py
│   ├── webhooks.py
│   ├── plans.py
│   └── middleware.py
├── auth/
│   └── middleware.py                   Validate X-User-Id, X-Organization-Id headers
```

---

## API Endpoints (additions)

```
# Billing (FastAPI)
POST   /api/billing/checkout             Create Mollie first payment, return checkout URL
POST   /api/billing/upgrade              Change subscription plan
POST   /api/billing/cancel               Cancel subscription
GET    /api/billing/subscription          Get current subscription details
GET    /api/billing/payments              List payment history
GET    /api/billing/usage                 Get current period usage
POST   /api/billing/webhook              Mollie webhook callback (not authenticated)

# Organization data (FastAPI, scoped by X-Organization-Id header)
# All existing endpoints now require and respect organization scoping
```

The Mollie webhook endpoint (`POST /api/billing/webhook`) is special: it is called by Mollie's servers, not by the browser. It must be publicly accessible without authentication. Mollie does not sign webhooks — instead, when you receive a webhook, you call Mollie's API to fetch the payment/subscription status. This is Mollie's recommended security model.

---

## Build Phase Integration

**Phase 1 (Landing page + walking skeleton)** — add:
- Better Auth setup (server config, hooks, client)
- Login and signup pages
- Email verification flow
- Organization creation on first signup
- Protected routes (redirect to login if not authenticated)
- `/try` page now requires login

**Phase 2 (Detection pipeline)** — add:
- Organization scoping on all database queries
- User ID recording on all write operations
- `X-User-Id` and `X-Organization-Id` header validation in FastAPI middleware

**Phase 3 (Review interface)** — add:
- Organization member list (for "assign to reviewer" dropdown)
- User avatars/names on detection cards (who reviewed what)
- Role-based UI: viewers see read-only interface

**Phase 5 (Export + audit)** — add:
- Audit log now shows real user names and links to user profiles
- Export records track who generated them

**New: Phase 5.5 — Billing:**
1. Mollie customer creation on organization creation
2. Plan definitions with limits
3. Plan enforcement middleware in FastAPI
4. Upgrade/downgrade flow with Mollie checkout
5. Webhook processing for payment status updates
6. Billing page in the frontend (plan selector, usage meter, payment history)
7. Grace period handling for failed payments
8. Usage tracking (documents per month)

**Phase 6 (Production hardening)** — add:
- Microsoft social login
- 2FA setup
- SSO plugin for enterprise organizations (Azure AD, KeyCloak)
- Rate limiting and abuse prevention

---

## Implementation Notes

1. **Better Auth and SQLAlchemy share the same database.** Better Auth creates its own tables (user, session, account, organization, member, etc.) and manages them. Your SQLAlchemy models reference these tables via foreign keys. Run Better Auth migrations first (`npx @better-auth/cli migrate`), then Alembic migrations for the WOO Buddy tables.

2. **The SvelteKit → FastAPI proxy** is implemented as `+server.ts` route handlers under `/api/`. SvelteKit catches these requests, validates the session, and forwards to FastAPI with trusted headers. This is a thin proxy — it adds headers and passes through the request/response body unchanged.

3. **Mollie webhooks need a publicly accessible URL.** In development, use a tunnel like ngrok or localtunnel. In production, the webhook endpoint is just `/api/billing/webhook` on your domain.

4. **Mollie does not sign webhooks.** When you receive a webhook with a payment ID, you must call Mollie's API (`GET /v2/payments/{id}`) to verify the payment status. Never trust the webhook payload alone.

5. **Plan enforcement should fail gracefully.** When a user exceeds their limit, don't show an error page — show a friendly message with a clear path to upgrade. "Je hebt dit maand 50 documenten verwerkt (limiet: 50). Upgrade naar Professional voor meer ruimte."

6. **The Gratis tier should be genuinely useful.** 3 documents per month and 1 dossier lets someone actually try the product and process a small Woo request. It's not a demo — it's a real tool with limits.

7. **Organization deletion is a sensitive operation.** It removes all dossiers, documents, detections, exports, and billing data. Require the owner to type the organization name to confirm. Consider a 30-day soft-delete period where the data can be recovered.

8. **User deletion must comply with AVG/GDPR.** Provide a "Verwijder mijn account" (Delete my account) option that removes all personal data. Dossier data owned by the organization should be anonymized (replace user references with "Verwijderde gebruiker") but not deleted, since the audit trail belongs to the organization.

9. **The Quick Try flow (`/try`) changes.** Previously it was anonymous. Now it requires login. If someone uploads a PDF from the landing page without being logged in, redirect to signup first, then resume the upload after authentication. Store the file temporarily (e.g., in the browser via the File API or in a temporary server-side storage) so the user doesn't have to re-upload after signing up.

10. **Microsoft social login is important.** Many Dutch government employees have Microsoft 365 accounts. "Inloggen met Microsoft" removes friction significantly. Configure the Microsoft provider in Better Auth with the appropriate Azure AD tenant settings. For multi-tenant support (any Microsoft account, not just one organization), use the `common` tenant endpoint.
