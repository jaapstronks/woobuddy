# 53 — Dossier / multi-document mode (architectural spike + implementation)

- **Priority:** P1 (once Phase E triggered)
- **Size:** XL (1–2 weeks for the spike + first vertical slice; additional work rolls into #54, #55)
- **Source:** Competitor landscape 2026-04 — INDICA and Novadoc both sell on multi-document workflows; WOO Buddy is single-document and `CLAUDE.md` flags a rewrite is needed
- **Depends on:** #32 (authentication), #33 (organizations) — both must be at least designed
- **Blocks:** #54 (cross-document dedup), #55 (cross-document name propagation), most of the Team-tier value proposition

## Why

The current app is deliberately single-document — a reviewer uploads one PDF, reviews it, exports it, done. That was the right shape for the prototype and is fine for the Gratis tier's individual-reviewer use case.

But a typical Woo-besluit covers **dozens to hundreds of documents** (emails, bijlagen, concepten) that must be treated as a **dossier**: same verzoek, same grondenstelsel, same reviewer team, repeated names and entities across documents. Every serious competitor (INDICA, Novadoc, ilionx+Tonic) builds around this unit, and the features that make teams pay — deduplication, name propagation, batch approve, dossier-level audit — all require it.

`CLAUDE.md` already acknowledges this:

> There is **no dossier concept, no document list, no cross-document state**. [...] Several backlog todos (organizations, document lifecycle, name propagation across documents, etc.) assume an older multi-document shape and will need rewriting when tackled.

This todo is the forcing function that produces that rewrite, as a deliberate architectural decision rather than ad-hoc reshaping during feature work.

## Shape of the spike

Before writing production code, produce a **written design doc** (`docs/design/dossier-mode.md`) covering:

### Data model

- [ ] What is a "dossier" in the schema? (new table `dossiers` with `id`, `organization_id`, `title`, `verzoek_reference`, `created_at`, `archived_at`)
- [ ] `documents.dossier_id` relationship, indexing strategy
- [ ] Does the dossier hold the *grondenstelsel* (which Woo-artikelen are pre-selected, default templates for reasons)? Yes — extract from per-document today to per-dossier default + per-document override.
- [ ] How does the review status roll up? (per-document `status`, plus derived dossier status like `in_review | ready | published`)

### Client-side state

- [ ] How does IndexedDB hold a dossier? Today: one PDF + one detection set per session. New: an array of `{docId, pdfBytes, detections, reviewStatus}` keyed by `dossierId`.
- [ ] What happens on close-tab / reopen? We need to pick up where we left off. This raises a question that the single-doc prototype deferred: **should client-side state survive across sessions for the anonymous tier?** Yes, via IndexedDB, but we must document the privacy implication in the trust copy and make "clear dossier" one-click.
- [ ] Memory budget: a 500-document dossier with average 2 MB PDF each = 1 GB in IndexedDB. IndexedDB handles this but we need a streaming loader (don't keep every PDF in RAM at once — only the currently-open document).

### Routing

- [ ] New routes: `/dossier/[dossierId]` (overview: list of documents, progress, actions), `/dossier/[dossierId]/[docId]` (review screen, existing `/review/[docId]` shape). The legacy `/review/[docId]` URL stays working as a single-doc shortcut.
- [ ] `/try` flow: user can still upload a single PDF and go straight to review (no dossier is created); this is the anonymous entry point and must keep working. Alternative flow: user creates a dossier and uploads multiple files into it.

### Server-side

- [ ] New endpoints: `POST /api/dossiers`, `GET /api/dossiers/:id`, `PATCH /api/dossiers/:id`. Detection endpoints gain a `dossier_id` scope query param.
- [ ] Anonymous dossiers: **do not persist server-side** (same rule as #50). Dossier metadata lives in IndexedDB until save.
- [ ] Post-auth save: bulk save flow uploads all documents' metadata + detections in one transaction.
- [ ] Rate limit `/api/analyze` per dossier + per user to prevent abuse.

### UX

- [ ] Dossier overview screen: table/list of documents, columns for filename, page count, detection count, status, last modified, reviewer. Bulk actions: analyze all, approve all, export all as zip.
- [ ] Navigation between documents within a dossier: prev/next, keyboard shortcuts, jump-list sidebar.
- [ ] Dossier-level export: one big .zip containing every redacted PDF + a combined DiWoo metadata bundle (ties #52 into dossier mode).
- [ ] Migration UX for existing single-doc users: "Promote to dossier" button that wraps the current document in a fresh dossier — keeps the feature discoverable without forcing dossier-first on everyone.

### Rewrites required in existing todos

- [ ] **#33 (Organizations)** — currently written against the old multi-document shape per `CLAUDE.md`. This todo's design doc supersedes it; update #33 to consume the dossier primitive.
- [ ] **#25 (Document lifecycle)** — extend to dossier lifecycle (draft dossier → in-review → approved → published).
- [ ] **#19 (Redaction log, done)** — verify it already keys off per-document cleanly; if it needs a `dossier_id` column, log a follow-up.
- [ ] **#31 (Redaction inventory CSV)** — gains a dossier-level variant that produces one CSV covering all docs.
- [ ] **#52 (DiWoo export, new)** — gains a dossier-bundle variant producing a multi-entry sitemap instead of one entry.
- [ ] **#20 (Bulk sweep, done)** — in-document today; cross-document variant is #55.

## Implementation slicing

Once the design doc is signed off, implement in three slices (don't try to ship the whole XL in one PR):

1. **Slice A — schema + empty dossier container** (M)
   - Backend migration, API endpoints, minimum React-less dossier overview page that creates and lists dossiers for a logged-in user
   - No review integration yet; dossier is an empty shell
   - Ship behind a feature flag

2. **Slice B — multi-doc upload + navigation** (M)
   - Upload multiple PDFs into a dossier, IndexedDB multi-doc storage, prev/next navigation in review screen
   - Per-document review works as today; no cross-document features yet
   - Keep `/try` single-doc path intact

3. **Slice C — dossier-level export + promote-to-dossier from single-doc** (M)
   - Zip bundle of redacted PDFs + combined DiWoo metadata (depends on #52 shipping first or in parallel)
   - "Promote to dossier" button in single-doc review
   - Feature flag flipped on for authenticated users

Cross-document features (#54 dedup, #55 name propagation, team approve flows) happen in subsequent todos, not in this one.

## Acceptance

- **Design doc** (`docs/design/dossier-mode.md`) exists, covers all sections above, and has been reviewed
- **Slice A** shipped and merged behind feature flag
- **Slice B** shipped: authenticated user can create a dossier, upload N documents, review them one at a time with prev/next nav, and each document's detections are persisted per-document
- **Slice C** shipped: dossier-level export produces a zip bundle of redacted PDFs + DiWoo metadata, IndexedDB holds a 500-document dossier without OOM
- Existing single-document `/try` → `/review/[docId]` flow is unchanged for anonymous users
- Feature flag off by default in production until a paying pilot asks for it (Phase E trigger)

## Not in scope

- Cross-document deduplication (#54)
- Cross-document name propagation (#55)
- Dossier-level approval gates with jurist review (belongs in Phase F, extends #25)
- Sharing dossiers across organizations (never — dossiers are always scoped to one org)

## Open questions

- Per-dossier custom wordlists as an extension of #21? Probably yes — a dossier often has the same "public officials" list. Defer to implementation; mention in design doc.
- Hard cap on documents per dossier? Soft rec of 500 for V1, no hard cap — let IndexedDB complain if the user pushes past limits.
