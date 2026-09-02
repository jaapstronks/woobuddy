# 70 — Structure consolidation: review page, stores, duplicated helpers, dead DB layer

> Status: aanzet · 2026-09-02 · TODO #70 · hangt samen met: —

- **Priority:** P2
- **Size:** L (split into 4–5 PRs, each under ~400 lines)
- **Source:** tighten-scan 2026-09-02

> Agent measurements on `origin/main` @ `83fecbb`; the LOC estimates are
> proposals, not measurements. Re-verify line numbers before editing.
> Second pass (review of PR #99, 2026-09-02): A, B, E confirmed; table C
> re-based (two "uses" counts were one too high, C5 named the wrong file, C9
> counted a non-NFKD normaliser); section F annotated.

## A. Review page decomposition (`routes/review/[docId]/+page.svelte`, 1305 lines)

| Extract | Lines today | Target |
|---|---|---|
| Top toolbar markup | 650-812 | `ReviewToolbar.svelte` |
| Banner stack (error/retry/a11y/lead/5-jaar) | 827-937 | `ReviewBanners.svelte` |
| Sidebar shell + split/merge panel | 990-1101 | `ReviewSidebar.svelte`, `SplitMergePanel.svelte` |
| Bottom bar (undo/zoom/fit) | 1104-1184 | `ReviewStatusBar.svelte` |
| Session bootstrap, fit observer, deep-link | 127-271 | `services/review-session.ts` |
| Export dialog state + 3 handlers | 282-396 | fold into `review-export.svelte.ts` |
| Keyboard glue | 452-507, 610-624 | `services/review-keyboard.ts` |

Residual page: ~250 lines of layout and prop wiring. While there: the
`$effect` at `:161-211` fires `initReviewSession` without a cancellation token
(switching `docId` mid-load assigns the wrong `pdfData`), and the deep-link
effect at `:233-247` strips `?detection=` even when `setPage` no-ops because
`totalPages === 0`. Both belong to the extracted session service.

## B. Store responsibilities

- `stores/review.svelte.ts` (214) mixes document identity, PDF viewport
  (~110 LOC) and UI chrome. Split three ways.
- `stores/detections.svelte.ts` (636) mixes CRUD, filters, selection, IDB
  persistence, analyze orchestration and analytics. `:138-152` and `:181-189`
  sanitize the same slice two ways; `session-state-store.ts` is the seam.
- `stores/review-export.svelte.ts:79,182,266` are three copies of one flow
  (busy → clear error → try → download → track → finally). One
  `runExportFlow(setBusy, fn)` removes ~60 lines.

## C. Duplicated helpers (measured ratios)

| Canonical | Uses | Hand-rolled | Where |
|---|---|---|---|
| `utils/review-status.ts` `isAcceptedRedaction` | 7 | 1 | `export-service.ts:44` (see #66) |
| page display `n+1` | 0 (no helper) | 7 | `PdfViewerToolbar:96`, `PageStrip:38,46`, `SearchPanel:221,249`, `DetectionList:156`, `log:694` |
| `utils/format.ts` `formatDate` | 0 | 1 (+1 variant) | `log/+page.svelte:368`; `onderbouwing/report.ts:292` `formatTimestamp` returns `{utc, ams}`, a different shape |
| `lib/api/client.ts` | 2 of 3 POSTs | 1 | `export-service.ts:11,14,87` (own `BASE`, raw fetch, no `ApiError`) |
| `analytics/plausible.ts` `track()` | 4 | 1 | `file-picker/analytics.ts:23-28` |
| `file-picker`: `parseContentLength`, `streamWithProgress` | — | byte-identical ×2 | `microsoft.ts:442,448` / `google.ts:186,192` → `file-picker/download.ts` |
| byte formatting | 0 | 2 | `ProviderPickerButtons:116-120`, `FileUpload:159` |
| backend `_pipeline_detection_from_ner` (`pipeline_engine.py:72`) | 7 | 3 | `title_match_rules.py:84,104`, `pipeline_custom_terms.py:29` |
| backend NFKD-lower normaliser | — | 3 impls | `name_engine.py:228,246`, `whitelist_engine/_text.py:154` (`:162` wraps it). Not `custom_term_matcher.py:44`: that one deliberately keeps diacritics, merging it is a behaviour change |
| backend `asyncio.to_thread` for CPU work | 1 | 2 | `export.py:166,172` (see #67) |

## D. Bigger files with natural seams

- `services/onderbouwing/report.ts` (1030): layout kernel (34-286) →
  `report/layout.ts`; tables (618-801) → `report/table.ts`; sections
  (288-617, 803-845) → `report/sections.ts`; orchestrator stays.
- `onderbouwing/bundle.ts` vs `diwoo/bundle.ts`: same concept, four names
  (`bundleOnderbouwing`/`buildPublicationBundle`,
  `deriveOnderbouwingFilename`/`deriveBundleFilename`), two zip paths. Extract
  `services/export-bundle.ts`.
- `HeroUploadPanel.svelte:25-35,63-109` holds ~90 lines of flow state that
  `upload-flow.ts:4-7` claims to own (`sourceTypeOf`, `buildLocalDocument`,
  the OCR-decision bridge).
- Naming: accept has four names (`accept`/`handleAccept`/`onRedact`/
  `onRedactWithArticle`), reject three (`reject`/`onUnredact`/`onKeep`);
  `loadPdfAndDetections` loads no detections and is imported as `loadReviewPdf`.

## E. Backend: the persistence layer is dead weight (Jaap decides)

No route imports `get_db` (`db/session.py:12`) or any ORM model; the five
tables in `models/schemas.py:70-276` are referenced only from tests and
`create_all`. Yet `main.py:28-72` runs 7 hand-written `ALTER TABLE … IF NOT
EXISTS` on every boot, `alembic` is a hard dependency with **no**
`migrations/versions/` directory, and `tests/conftest.py:86-97` requires a
live Postgres for every HTTP test (CI spins one up at `test.yml:50-67`) even
though no request touches a database.

Options: (1) keep Postgres wired but delete the ALTER block, make the DB
fixture opt-in per test, drop alembic until #32 needs it; (2) remove the DB
from the default path entirely until #32/#33 land (docker compose becomes
API-only for self-hosters). Both keep the models file. This is a product
decision about what "self-host" means today.

Also orphaned: `pdf_engine.extract_text` (`:128-186`, tests only),
`get_page_count` (`:330-335`, zero callers), `tests/diagnostic_newdocs.py`
(a script collected as a test module), `title_match_to_detection` typed
`| None` but never returns None (2 dead branches at `pipeline_engine.py:442,453`).

## F. Dead exports (zero importers, verified by grep; drop `export` or delete)

Most of these are still used inside their own file, so only the `export`
keyword is dead (`pulseOverlay`, `BBOX_SLACK_PT`, `makeStatusCommand`,
`reanalyzeWithLists`, `siteMode`, `getOverlayStyle`); genuinely unused code:
`deleteSessionState`, `getCachedTooiVersion` (also re-exported at
`diwoo/index.ts:14`).

Frontend: `pdf-overlay-effects.ts:18` `pulseOverlay`;
`session-state-store.ts:157` `deleteSessionState`; `pdf-store.ts` `deletePdf`,
`getStorageEstimate`; `extraction-store.ts` `deleteExtraction`; `idb.ts`
`IdbError`, `DB_NAME`, `DB_VERSION`; `selection-bbox.ts:44` `BBOX_SLACK_PT`;
`boundary-edit-geometry.ts:29-30`; `review-actions.ts:37` `makeStatusCommand`;
`list-panel-actions.ts:25` `reanalyzeWithLists`; `config/site.ts:21`
`siteMode`; `upload-flow.ts:38-43` three constants; `diwoo/tooi-loader.ts:36`
`getCachedTooiVersion`; `PdfViewer.svelte:1-6` module re-exports;
`pdf-overlay-draw.ts:178` `getOverlayStyle` ("exported for unit testing",
no test exists). Unreachable UI: the Art. 5.3 banner (`+page.svelte:920-937`,
`five_year_warning` hard-coded `false` at `review.svelte.ts:82` and `HeroUploadPanel.svelte:80`),
`Tier2Card.svelte:183-187` "Gepropageerd" (`propagated_from` always null),
the Reviewer column at `log/+page.svelte:758`.
Deps: `@testing-library/svelte` (0 refs; `vitest.config.ts:31` is `node`
env so component tests cannot run anyway). Static: `static/samples/*.png`
(~500 KB, 0 refs), `static/shoelace/assets/icons` (8.4 MB, bypassed by the
jsdelivr `setBasePath` at `routes/review/+layout.svelte:8`),
`static/og-image.gen.py` (served publicly).

## Gate

- `knip` (or `ts-prune`) in CI for unused exports; `ruff`'s `F401`/`F841`
  already cover Python.
- A `displayPage()`/`toStoredPage()` pair in `utils/` with a grep-test that
  no component does `+ 1` on a page index.
- File-size guard: fail `npm run check` on any `.svelte` over 600 lines.

## Acceptance criteria

- [ ] `+page.svelte` under 400 lines; each extracted piece has one owner.
- [ ] Every row in the ratio table reads N/0.
- [ ] Decision on E recorded here and in `docker-compose.yml`.
