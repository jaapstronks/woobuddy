# 41 — Analytics (Plausible)

- **Priority:** P3
- **Size:** S (< 1 day)
- **Source:** Testing & Polish briefing, "Analytics" section
- **Depends on:** #39 (Deployment — needs a live site)
- **Blocks:** Nothing

## Why

Basic analytics on the landing page to understand visitor behavior and conversion. Must be privacy-friendly — Google Analytics is inappropriate for a government privacy tool.

## Scope

- [ ] Set up Plausible (EU-hosted, no cookies, no consent needed) or Fathom as alternative
- [ ] Landing page only — no analytics in the app interface
- [ ] Track: page views, "Probeer gratis" clicks, signup conversion, document upload count
- [ ] Nothing else — no session recording, no heatmaps, no user tracking

## Acceptance Criteria

- Plausible dashboard shows landing page traffic
- No cookie consent required (Plausible is cookieless)
- Analytics script only loads on public pages, not in `/app/*`
