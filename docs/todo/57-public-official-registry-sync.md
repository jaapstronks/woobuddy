# 57 — Public-official registry sync (shared org lists)

- **Priority:** P2 (Team-tier feature)
- **Size:** M (1–3 days)
- **Source:** Competitor landscape 2026-04 — natural extension of #13 and #17; shared-lists are a team-tier value driver
- **Depends on:** #17 (per-document referentielijst — done), #33 (organizations)
- **Blocks:** Nothing

## Why

#13 ships a static list of generic functietitels (wethouder, burgemeester, raadslid, …) and #17 lets a reviewer build a per-document reference list of public officials. But each gemeente has its own specific public officials — the college B&W of gemeente Utrecht in 2026 is Sharon Dijksma plus seven named wethouders, and reviewers in Utrecht want those names pre-loaded so they don't re-teach the tool every time.

Most gemeentes publish their college + raadsleden on a predictable URL (e.g. `https://www.utrecht.nl/bestuur-en-organisatie/college-van-b-en-w/`) and frequently also in [OpenRaadsinformatie](https://openraadsinformatie.nl) as structured data. A Team-tier feature that syncs these per organization gives the org's reviewers a shared, always-fresh public-official list without any manual data entry.

This is a Team-tier differentiator: the Gratis tier gets the static functietitel list (#13) and per-document additions (#17); the Team tier gets a shared, auto-refreshing org-specific list.

## Scope

### Data model

- [ ] New `OrganizationPublicOfficialList` scoped per `Organization`: `[{name, role, source, last_synced_at, active}]`
- [ ] Each entry has a `source` field (e.g. `openraadsinformatie`, `manual`, `scraper:gemeente-utrecht`) so reviewers can see provenance and un-trust specific sources

### Sync sources (server-side, scheduled)

- [ ] **OpenRaadsinformatie** as primary source — it's an open dataset covering most Dutch gemeenten. A background job (daily) fetches college + raadsleden for each registered organization and updates the list.
- [ ] **Gemeente-specific scrapers** as fallback for orgs not well-covered by ORI. Start with a small allowlist of patterns (5–10 major gemeenten hand-coded), add more per pilot request.
- [ ] **Manual CSV import** for orgs that don't have a public source (ministries, ZBO's, small organisaties): reviewer uploads a CSV; manually maintained.
- [ ] **No LLM, no scraping at analyze-time**: the sync is a scheduled background job, not part of the hot path. Cache is refreshed asynchronously.

### UX

- [ ] Organization settings page: "Publieke functionarissen" section showing the current list with source badges, last sync time per source, and a "force refresh" button.
- [ ] Manual add/remove with required reason (for audit trail — #19 logs who added whom).
- [ ] On review: entries from the org list appear in the same public-official UI as #17's per-document list, differentiated by a subtle "org-wide" badge. Reviewer can override per-document if the context demands it (e.g. a former wethouder whose tenure ended during the period covered by the document).

### Privacy / legal

- [ ] Public-official names are public information by definition (published on gemeente websites). Storing them server-side is defensible.
- [ ] Former officials: retain in the list with `active: false` + `ended_at` so historical documents (where they were still in office) still benefit from the auto-recognition.
- [ ] Right-to-be-forgotten consideration: officials who have requested removal from public lists should be removable; add an admin action.

### Self-host

- [ ] Self-hosters can enable/disable individual sync sources via config. Default-on for OpenRaadsinformatie, default-off for hard-coded scrapers (less robust), always-available for manual CSV.

### Tests

- [ ] Unit: ORI fetcher correctly parses a known organization response
- [ ] Unit: a manual entry shadows an auto-synced entry if the reviewer has explicitly edited it
- [ ] Integration: new organization triggers initial sync; subsequent dossier analyses see the list available

## Acceptance

- An authenticated organization can view, edit, and force-refresh its public-official list
- Scheduled background job keeps OpenRaadsinformatie-sourced entries fresh daily
- Reviewers in that org see their shared list applied automatically in document review
- Self-host can disable sync sources or run manual-only

## Not in scope

- International official lists (non-Dutch) — scope is Dutch gemeenten/provincies/ministeries
- Lookups by photo/face — out of scope, privacy minefield
- AI-based "is this person a public official" inference — explicitly out of scope per no-LLM rule
- Real-time sync at upload time — async only

## Open questions

- Do we want to bundle a curated scraper list for the top-20 gemeenten, or leave all scrapers pilot-driven? Recommendation: start with ORI only, add hand-written scrapers only if a pilot's ORI coverage is insufficient. Don't pre-build speculative scrapers — they rot.
- Rate-limiting / respectful crawling for scrapers: default 1 request/minute per source, cache aggressively, honor robots.txt.
