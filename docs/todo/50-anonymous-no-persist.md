# 50 — Anonymous analyze: no server persistence

- **Priority:** P1
- **Size:** L
- **Depends on:** 32 (authentication)
- **Blocks:** the trust claim in `#00` for unauthenticated users
- **Notion:** [Ship #50 — anonymous /api/analyze no server persistence](https://www.notion.so/34d11fb08c9e81c3b0afe4cd328e0088)

## Why

`CLAUDE.md` declares:

> Anonymous `/api/analyze` requests must not persist anything to PostgreSQL. No `Document` row, no `Detection` rows. Detection metadata is computed in memory and returned. Persistence kicks in only when the user logs in and explicitly chooses to save.

Today every `/try` visitor triggers `POST /api/documents` (a `Document` row) and `POST /api/analyze` (a `Document.status` update + `Detection` rows). The client-first trust story therefore overstates what actually happens on the hosted tier: metadata still lands in Postgres without the user ever logging in or choosing to save.

## Scope

- `POST /api/analyze` gains an anonymous mode that returns the full detection payload in the response body and persists nothing. The authenticated "save" mode persists as today.
- `POST /api/documents` becomes unnecessary on the anonymous path — document metadata lives only in the browser until save.
- Detection PATCH/split/merge on anonymous documents operate on in-browser state (IndexedDB), not on Postgres rows. Auth unlocks server-side PATCH as a sync point.
- Frontend `detectionStore` can already round-trip detections through the API; it needs a storage adapter that swaps between "server-backed" (authed) and "IndexedDB-backed" (anonymous).

## Acceptance

- Anonymous upload → analyze → review → export produces **zero** rows in `documents` and `detections` tables.
- Logged-in user can save the current review, which triggers a one-shot `POST /api/documents` + bulk `POST /api/detections` from the IndexedDB state.
- Rate limiting on `/api/analyze` still works without any `Document` row to anchor on.
- `AnalyzeResponse` is backward-compatible: currently returns `detection_count`; add a full `detections: list[DetectionResponse]` field used by the anonymous path.

## Why this is not a code-quality refactor

Implementing it requires auth to exist (#32) and a rewrite of the client-side review store to hold detections locally. It is a feature change, not a cleanup — tracked here so the violation is not forgotten.
