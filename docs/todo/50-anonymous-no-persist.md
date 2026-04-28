# 50 — Anonymous analyze: no server persistence

- **Priority:** P1 (launch blocker — the trust claim diverges from reality today)
- **Size:** M (anonymous path only — see "Scope split" below)
- **Depends on:** Nothing
- **Blocks:** The trust claim in `#00` for unauthenticated users
- **Notion:** [Ship #50 — anonymous /api/analyze no server persistence](https://www.notion.so/34d11fb08c9e81c3b0afe4cd328e0088)

## Why

`CLAUDE.md` declares:

> Anonymous `/api/analyze` requests must not persist anything to PostgreSQL. No `Document` row, no `Detection` rows. Detection metadata is computed in memory and returned. Persistence kicks in only when the user logs in and explicitly chooses to save.

Today every visitor to the landing-page upload flow (the drop zone embedded at `/#try`, route `/` — the standalone `/try` route is a permanent 308 redirect) triggers `POST /api/documents` (a `Document` row) and `POST /api/analyze` (a `Document.status` update + `Detection` rows), plus `PATCH /api/detections/...` and the page-reviews / reference-names / custom-terms write endpoints during review. The client-first trust story therefore overstates what actually happens on the hosted tier: metadata still lands in Postgres without the user ever logging in or choosing to save.

A CISO who reads `/privacy` and inspects the network tab will catch this and burn the launch.

## Scope split (decided 2026-04-28)

The original todo coupled two things that turn out to be independently shippable:

- **50a — Anonymous-zero-rows (this todo).** Anonymous flow writes nothing to Postgres. Detections, page-reviews, reference-names, custom-terms all live in browser memory (or IndexedDB where cross-tab persistence makes sense). Ships as a pre-launch gate.
- **50b — Authenticated "save" mode (deferred to Phase E).** When a logged-in reviewer chooses to save the current session, the local state is bulk-uploaded to Postgres. This was the original framing's `Depends on: #32`. Since the open-source launch goes out without auth, 50b is unbuildable and untestable today — and even when #32 lands, it is a feature, not a privacy fix. Tracked separately in the backlog when auth lands.

The Notion page captures this split in one line: *"only the anonymous-zero-rows half needs to ship."*

## Scope (50a only)

### Backend

- `POST /api/analyze` accepts requests **without** `document_id`. Anonymous mode: skip `get_document_or_404`, skip `Document.status` mutation, run the pipeline in memory, return the full detection list inline (with server-generated UUIDs), persist nothing.
- The save-mode (request *with* `document_id`) keeps current behavior — it stays in-tree for 50b but has no caller from the frontend until auth ships.
- `AnalyzeResponse` extended with `detections: list[DetectionResponse]`. Backward-compatible: existing fields (`document_id`, `detection_count`, `page_count`, `structure_spans`) keep their meaning.
- Rate limiting still works without a `Document` row to anchor on (already IP-based via `slowapi`).
- `POST /api/export/redact` accepts the detection list inline in the request body instead of reading from the DB. The redaction step itself stays server-side and ephemeral (PDF in memory, redacted PDF streamed back, original never written to disk — unchanged).

### Frontend

- `upload-flow.ts` drops `registerDocument()`. Document UUID is generated client-side via `crypto.randomUUID()`.
- `detectionStore` becomes local-only on the anonymous path:
  - `analyze()` takes detections directly from the response into local state — no `load()` follow-up.
  - `review` / `accept` / `reject` / `defer` / `createManual` / `remove` / `adjustBoundary` / `split` / `merge` are pure local mutations with client-generated UUIDs. No PATCH/POST/DELETE.
- Page-reviews (#10) removed from the anonymous path. They come back when auth lands and cross-session state has somewhere to live.
- Reference-names (#17) and custom-terms (#21) become local-only stores. They already travel inline in the analyze request body, so the pipeline keeps working — what disappears is the GET/POST/DELETE round-trips for managing the list itself.

## Acceptance

- Anonymous upload → analyze → review → export produces **zero** rows in `documents` and `detections` tables.
- All review actions (accept/reject/defer/manual redact/boundary adjust/split/merge) work without any backend writes.
- Export still produces a valid redacted PDF when the detection list is sent inline.
- Rate limiting on `/api/analyze` still works without a `Document` row to anchor on.
- `AnalyzeResponse` adds a `detections: list[DetectionResponse]` field; existing fields unchanged.
- Integration test: full flow → `SELECT COUNT(*) FROM documents` and `SELECT COUNT(*) FROM detections` both return 0.

## Why this is not a code-quality refactor

It is a feature change with significant frontend reshaping (detection store going from server-of-record to in-browser-state) and a small backend addition. Tracked here so the trust-claim divergence is not forgotten and the work can be sequenced as a launch gate.
