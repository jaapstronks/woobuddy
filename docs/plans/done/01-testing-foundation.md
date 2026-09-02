# 01 — Testing Foundation

- **Priority:** P0
- **Size:** L (3–7 days)
- **Source:** Testing & Polish briefing, Section 1
- **Depends on:** #00 (Client-first architecture — tests must reflect the new data flow)
- **Blocks:** Everything else benefits from tests existing
- **Status:** Done

## What Was Built

### Backend (pytest) — 76 tests

- [x] Set up pytest with `httpx.AsyncClient` for async endpoint testing
- [x] Configure a test PostgreSQL database (`woobuddy_test`, separate from dev)
- [x] `test_ner_engine.py` (34 tests) — Tier 1 regex + validation (BSN 11-proef, IBAN, phone, email, postcode, license plates, credit cards) + Tier 2 Deduce NER + combined detect_all with confidence boosting
- [x] `test_llm_engine.py` (14 tests) — Pipeline orchestration: tier assignment, public official filtering, environmental content detection, bounding box resolution, empty/mixed inputs
- [x] `test_propagation.py` (12 tests) — Propagate/undo across documents, case-insensitive matching, guard rails (only persons, only reviewed), full cycle (propagate → undo → re-propagate)
- [x] `test_endpoints.py` (13 tests) — Dossier CRUD, detection list/filter/update, propagation via HTTP, health check, 404/422 error cases
- [x] `conftest.py` — Test DB fixtures with NullPool (avoids asyncpg connection reuse issues), per-test transaction rollback for service tests, table truncation for endpoint tests, seed_db fixture for pre-seeding data

### Frontend (Vitest) — 22 tests

- [x] Set up Vitest with SvelteKit-compatible config
- [x] `woo-articles.test.ts` (13 tests) — All 12 article codes present, getArticleLabel formatting, isAbsoluteGround/isRelativeGround classification, tier assignments
- [x] `tiers.test.ts` (9 tests) — Tier labels/descriptions, confidenceToLevel thresholds (0.85 high, 0.6 medium), boundary values

### CI (GitHub Actions)

- [x] `.github/workflows/test.yml` with frontend-unit and backend jobs
- [x] Backend job uses `services: postgres` container (PostgreSQL 16)
- [x] Backend job runs ruff lint + pytest
- [x] Frontend job runs svelte-check + vitest

## Known Limitations

- **International phone numbers (+31...)**: The Tier 1 regex uses `\b` word boundary which doesn't match before `+`. Documented as a test assertion (`test_international_mobile_detected`).
- **Deduce salutation capture**: Deduce sometimes captures "De heer Jan de Vries" instead of just "Jan de Vries". Public official matching depends on the exact detected text. Tests use input text where Deduce detects just the name.
- **No E2E/Playwright tests yet** — separate todo, needs auth first.
- **No component tests yet** — utility tests only for now; component tests require browser mode setup.

## Not in Scope (as planned)

- Playwright E2E tests (separate todo, needs auth first)
- Full coverage of all endpoints (incremental, added with each feature)
