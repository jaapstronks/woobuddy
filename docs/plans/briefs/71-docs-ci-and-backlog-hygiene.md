# 71 — Docs, CI and backlog hygiene (scan 2026-09-02)

> Status: aanzet · 2026-09-02 · TODO #71 · hangt samen met: —

- **Priority:** P2 (P1 for the first three items: they mislead contributors today)
- **Size:** S–M, mostly deletions and one-line edits
- **Source:** tighten-scan 2026-09-02

## Now (misleading today)

1. **#50 is shipped but still open.** `backend/app/api/analyze.py:7`,
   `export.py:3`, `tests/test_analyze_api.py:136-169` all prove it. The
   bookkeeping commit `4e322ed` sits unmerged on `origin/chore/close-50`.
   Open the PR, merge, done. This is the exact violation CLAUDE.md's "never
   leave a fully-implemented todo" rule names.
2. **CONTRIBUTING links a file that is not in the repo.** `CONTRIBUTING.md:11,98`
   link `CLAUDE.md`, which `.gitignore:30` ignores (untracked since #51).
   Either track a scrubbed public copy or point contributors at README only.
3. **CI does not run what CONTRIBUTING mandates.** `CONTRIBUTING.md:46` says
   `mypy app/` and `ruff format --check`; `.github/workflows/test.yml:79-80`
   runs only `ruff check app/` + `pytest`. Current state on `main`:
   - `mypy app/` → 3 errors (`role_engine.py:324` union-attr; missing stub
     config for `fitz` and `deduce`).
   - `ruff format --check app/ tests/` → 13 files would reformat.
   - `ruff check tests/` → 5 findings (4 auto-fixable import sorting, 1 unused
     variable at `tests/test_pdf_engine.py:71`).
   - Frontend has no lint or format step at all, yet `microsoft.ts:51,406,457`
     and `google.ts:30,147,200` carry six `eslint-disable` pragmas for an
     ESLint that is not installed.
   - `scripts/bump-tooi-lists.mjs --check` is documented but not in CI.
   Add the steps or delete the instructions; do not leave both.
4. **`docs/plans/TODO.md:7,212` say the Ollama provider "stays in-tree as a
   dormant revival path"**; `CLAUDE.md:17` and commit `62a4b53` say it was
   removed. Code agrees with CLAUDE.md. `done/WOO_BUDDY_TODO.md` still points
   at `backend/app/llm/`.

## Backlog rewrite (assume a shape the code no longer has)

| # | Verdict | Action |
|---|---|---|
| 25 document lifecycle | server `status` on a row nothing writes | rewrite client-side or drop |
| 26 draft preview | routes `/app/dossier/[id]/…` do not exist | rewrite paths |
| 27 draft comments | `draft_comments` keyed on server detection IDs (gone post-#50) | rewrite or drop |
| 28 export versioning | `exports` table + removed `/api/documents/{id}/export` route | rewrite |
| 31 redaction inventory | ~70% shipped (`diwoo/csv.ts:53`, bundled at `onderbouwing/bundle.ts:72-77`) | shrink to XLSX + a button on the log page |
| 38 email service | proposes Resend/Nodemailer; Scaleway TEM + Listmonk already shipped | shrink to what is left |
| 46 | line ref `FileUpload.svelte:26` is wrong (`:37`) | fix ref |
| 58 | depends on `RedactionLogEntry` + `Dossier` tables that do not exist | mark the data section as fiction |
| two `48-*.md` in `done/` | number collision, both legitimate | renumber one to 72 |

## Reference docs

- `docs/reference/ARCHITECTURE.md` is ~70% fiction past its warning banner:
  `app/llm/provider.py` (:111), `storage.py`/`export_engine.py`/`audit.py`
  (:123-125), MinIO (:146), six tables incl. `audit_log` (:154-163),
  `/api/dossiers` (:287-289). Gut it to ~40 current lines or archive it.
- `THIRD_PARTY_LICENSES.md` misses pikepdf, structlog, slowapi, asyncpg,
  pydantic-settings, python-multipart, pdf-lib, fflate, tesseract.js, and the
  `medewerkers_gemeenten.csv` data source.
- `README.md:28` ("alleen beslissingen worden bewaard": nothing is stored
  anymore), `:68` (`/try` is a redirect).
- `CLAUDE.md` (local, untracked): `:39,236` and `:86` link todos that moved to
  `done/`; the Hero-video section points at `Hero.svelte` but the `<video>`
  lives in `MarketingIntro.svelte:88`; the Shoelace list misses 7 components
  in use (`sl-button-group`, `sl-divider`, `sl-dropdown`, `sl-icon`,
  `sl-menu`, `sl-menu-item`, `sl-option`).
- Docs missing for self-hosters: `PUBLIC_SITE_MODE` (the `(hosted)/+layout.ts:12`
  404 guard), `npm run setup:tesseract`, and that `npm run check` needs
  `PUBLIC_API_URL` set (`test.yml:26` is the only place that says so).

## Repo hygiene

- `scripts/woo_contacts_named.csv`: real named municipal officials,
  referenced by nothing, in a public MIT repo. Delete (the inbox variant is
  department labels only and harmless; `split_woo_contacts.py` and
  `create-test-pdfs.py` are also unreferenced).
- `tests/test-jsons/` (8 files, 117 KB): debug downloads from
  `debug-export.ts:121`, referenced by no test. `besluit_ambtenaar.detections (2).json`
  is the only copy (browser collision suffix). Delete or wire as golden files.
- `tests/fixtures/README.md` omits `demo-video.pdf`,
  `woo-testbestand-vertrouwelijk.txt` (0 references) and the two generator scripts.
- Root `.gitignore:60` `/*.png` currently hides 5 screenshots (1 MB); point
  the screenshot workflow at a scratch dir instead.
- Backend has no lockfile (`pip install .` resolves fresh per build);
  `routes/review/+layout.svelte:8` pins Shoelace CDN `@2.20.1` while
  `package.json` floats `^2.20.0`.

## Comment hygiene (inventory, not urgent)

- Stale and wrong: `pipeline_types.py:21-22,48,61,66-68` (talk of persisting
  rows), `export.py:5-7` (no disk writes), `deploy/Caddyfile:32` (old route),
  `middleware/request_id.py:32-35` (`SENSITIVE_PATH_PREFIXES` lists a deleted
  route, misses `/api/export`, and is never read), `boundary-edit-geometry.ts:11`
  (page 1-based: it is 0-based), `review-pdf-loader.ts:88-91`,
  `log/+page.svelte:295-298` (backend 4xx on delete: no such route),
  `leads.py:97` ("the Brevo attributes"), `idb.ts:44-46` (v3 vs v4).
- Provenance narration (~22 sites): "extracted from …", "previously owned …",
  "as we used to", "moved to pipeline_types.py". Delete; git has it.
- Issue-number tags inline: 135 in the review tree, 69 in the rest of the
  frontend. Keep one `Ref: #NN` per file header at most.
- Remaining CIIIC mention: `backend/tests/test_ner_engine.py:207`.

## Gate

- CI runs `mypy`, `ruff format --check`, `ruff check app/ tests/`, and a
  frontend formatter; `CONTRIBUTING.md` lists exactly those commands.
- A CI grep that fails on `backend/app/llm`, `Brevo`, `CIIIC` outside `done/`.

## Acceptance criteria

- [ ] `chore/close-50` merged; #50 struck in README.
- [ ] CI and CONTRIBUTING agree on the exact command list; all green on `main`.
- [ ] #25–#28, #31, #38 rewritten or deleted with a note in "Briefings Not Adopted".
- [ ] `scripts/woo_contacts_named.csv` and `tests/test-jsons/` gone or wired.
