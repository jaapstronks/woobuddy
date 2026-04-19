# 41 — Analytics (Plausible, self-hosted)

- **Priority:** P1
- **Size:** S (< 1 day frontend; server work separate)
- **Source:** Testing & Polish briefing, "Analytics" section
- **Depends on:** #39 (Deployment — needs a live site + a server to host Plausible)
- **Blocks:** Nothing

## Why

Basic analytics to understand visitor behaviour and the Phase-D conversion funnel (`/try` starts → document converted → redactions reviewed → export completed → email signup). Google Analytics is inappropriate for a government privacy tool, and the hosted Plausible tier is a recurring €/month the project doesn't need to pay because the server used for other sites (CIIIC, etc.) can host a single Plausible Community Edition instance that serves many subdomains.

## Decision

Plausible Community Edition (AGPL, free), self-hosted on a shared VPS, using a **site identity owned by WOO Buddy** (`analytics.woobuddy.nl`) — not the host server's domain. That way the eventual migration away from the initial host is a DNS flip, not a frontend code change.

## Scope (frontend — done)

- [x] `PUBLIC_PLAUSIBLE_DOMAIN`, `PUBLIC_PLAUSIBLE_SRC`, `PUBLIC_PLAUSIBLE_API` env vars (empty by default → analytics fully disabled; script never injected).
- [x] `$lib/analytics/plausible.ts` — SSR-safe wrapper with `track()` and `pageview()`, both no-op when disabled.
- [x] `$lib/analytics/events.ts` — enumerated event names + typed props. Adding a new event is a deliberate two-step change.
- [x] Script injection via root `+layout.svelte` (client-only, `onMount` + `afterNavigate`). URL normalized so `/review/<uuid>` shows up as `/review/:docId` in the dashboard.
- [x] CSP updated to allow `https://analytics.woobuddy.nl` in `script-src` and `connect-src`.
- [x] Four custom events wired:
  - `document_converted` — fires after a successful `ingestFile()` in the Hero upload panel, including both the OCR-accept and OCR-decline branches. Props: `source_type`, `page_bucket`, `used_ocr`.
  - `redaction_confirmed` / `redaction_rejected` — fires in `detectionStore.review()` only when the reviewer's action transitions to a terminal state. Props: `tier`, `entity_type`. Never entity text.
  - `export_completed` — fires in `reviewExportStore.runExport()` after a successful redacted-PDF download. Props: `redaction_bucket`, `page_bucket`.

## Scope (ops — to be completed out of tree)

- [ ] Provision a small VPS (Scaleway PLAY2-NANO or equivalent, ~€5–€8/mo, EU region).
- [ ] Stand up Plausible Community Edition via the official `docker-compose.yml` (Plausible + Postgres + ClickHouse), behind Caddy/Traefik for automatic TLS.
- [ ] Configure `analytics.woobuddy.nl` as a CNAME/A record pointing at the VPS. Same pattern for `analytics.ciiic.nl` and any other site sharing the instance.
- [ ] Add `woobuddy.nl` as a site in the Plausible UI. Set up four goals matching the event names above.
- [ ] Set `PUBLIC_PLAUSIBLE_DOMAIN=woobuddy.nl` in the production `.env` and deploy. Verify a pageview + one of each custom event land in the dashboard.
- [ ] Soften the "geen trackers" copy on the landing page, Hero chip, Footer, meta/OG descriptions, and `og-image.gen.py` in the **same** PR that enables `PUBLIC_PLAUSIBLE_DOMAIN` in production. Suggested replacements: `Geen cookies, geen fingerprinting` / `Geen advertentietrackers` / `Cookieloos bezoekers­tellen`. The cookies page already mentions Plausible correctly.

## Privacy posture

- No cookies, no `localStorage`, no fingerprinting. Plausible's uniqueness heuristic is a 24h-rotating hash of `IP + UA + domain + salt`; raw IPs never leave the edge.
- Self-hosted on EU infrastructure under WOO Buddy's own DPA — no third-party data processor.
- CSP-pinned to the single self-hosted origin.
- Event props are enumerated in `events.ts` and reviewed per PR. Never filenames, entity text, or exact counts that could fingerprint a specific document.

## Acceptance criteria

- With empty `PUBLIC_PLAUSIBLE_DOMAIN`, no script is injected and no network traffic goes to any analytics origin (verified in DevTools).
- With the env set in production, the Plausible dashboard receives:
  - Pageviews on landing, `/roadmap`, `/privacy`, `/cookies`, and `/review/:docId` (collapsed, not one row per document).
  - One `document_converted` event per successful upload.
  - One `redaction_confirmed` or `redaction_rejected` per reviewer action.
  - One `export_completed` per successful redacted-PDF download.
- `/cookies` page reflects the actual analytics stack (already correct).
- Landing-page copy does not claim "geen trackers" while Plausible is live.
