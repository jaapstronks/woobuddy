# 26 — Email Service

- **Priority:** P2
- **Size:** M (1–3 days)
- **Source:** Testing & Polish briefing, Section 4
- **Depends on:** #24 (Auth — email verification needs email delivery)
- **Blocks:** Nothing (auth can use basic SMTP initially)

## Why

Better Auth needs emails for verification, password reset, and invitations. Billing needs emails for payment receipts and failure notifications. A production email service is needed before real users.

## Scope

### Dev setup

- [ ] Nodemailer with SMTP for development (Gmail SMTP or Mailhog for local)
- [ ] All emails functional via basic SMTP

### Production service

- [ ] Evaluate and set up: Resend (recommended), Scaleway TE, or Mailgun EU
- [ ] Configure with proper SPF/DKIM/DMARC for `woobuddy.nl` domain

### Email templates (all in Dutch)

- [ ] "Bevestig je e-mailadres" — email verification after signup
- [ ] "Wachtwoord herstellen" — password reset link
- [ ] "[Org] nodigt je uit voor WOO Buddy" — organization invitation
- [ ] "Betaling ontvangen" — payment receipt
- [ ] "Betaling mislukt" — payment failure notification
- [ ] "Je abonnement verloopt binnenkort" — downgrade warning (3 days before)
- [ ] "Je account is teruggezet naar Gratis" — post-downgrade notification

### Template design

- [ ] HTML templates: WOO Buddy logo, single CTA button, professional styling
- [ ] Plain-text fallback for all templates
- [ ] No marketing content — functional emails only

## Acceptance Criteria

- All auth flows send emails that arrive reliably
- Templates render correctly in common email clients (Outlook, Gmail)
- Dutch language, professional tone, clear CTA
