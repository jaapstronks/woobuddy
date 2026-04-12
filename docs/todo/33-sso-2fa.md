# 33 — Microsoft SSO & 2FA

- **Priority:** P3
- **Size:** M (1–3 days)
- **Source:** Auth & Billing briefing, social login + 2FA sections
- **Depends on:** #24 (Authentication)
- **Blocks:** Nothing

## Why

Many Dutch government employees have Microsoft 365 accounts. "Inloggen met Microsoft" removes friction significantly. 2FA adds a trust layer important for government tools. These are differentiators, not launch blockers.

## Scope

### Microsoft social login

- [ ] Configure Microsoft provider in Better Auth
- [ ] Azure AD multi-tenant (`common` endpoint) to support any Microsoft account
- [ ] `MICROSOFT_CLIENT_ID` and `MICROSOFT_CLIENT_SECRET` env vars
- [ ] "Inloggen met Microsoft" button on login/signup pages
- [ ] Handle account linking (Microsoft login + existing email/password account for same email)

### 2FA

- [ ] Enable Better Auth 2FA plugin
- [ ] TOTP-based (authenticator app) setup flow
- [ ] `<TwoFactorSetup>` component in personal settings
- [ ] 2FA challenge during login when enabled

### Future: SSO plugin

- [ ] Better Auth SSO plugin for enterprise organizations (Azure AD, KeyCloak)
- [ ] Per-organization SSO configuration
- [ ] *Evaluate only* — full implementation depends on enterprise customer demand

## Acceptance Criteria

- Users can sign up and log in with their Microsoft account
- 2FA can be enabled in settings and is enforced during login
- Account linking works: Microsoft login finds existing account by email

## Not in Scope

- Google social login (not relevant for Dutch government)
- Passkeys (future enhancement)
- Mandatory 2FA per organization (future admin setting)
