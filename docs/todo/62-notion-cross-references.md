# 62 — Notion ↔ docs/todo cross-references

- **Priority:** P3 (housekeeping)
- **Size:** S (a couple of hours)
- **Source:** Process refinement 2026-04
- **Status:** Partial — convention adopted; backfill incomplete.

## Why

`docs/todo/` is the implementer's view of the backlog; the Notion "Woobuddy Todos" DB is the cross-tool tracker Jaap + Jeroen review during planning. Today the two systems drift: a status change in one isn't visible in the other, and clicking from a Notion "Ship #NN" page to the actual scope-of-work file requires manual lookup.

A `github-url` URL property was added to the Notion DB on 2026-04-26 to enable structured cross-references. This todo tracks the one-time backfill and the ongoing convention.

## Convention

- **Notion → GitHub:** every "Ship #NN" page in the Notion DB sets the `github-url` URL property to the GitHub permalink of the matching `docs/todo/NN-*.md` (or `docs/todo/done/NN-*.md` once moved). Use `https://github.com/jaapstronks/woobuddy/blob/main/...` (rendered) — not `raw/main`.
- **GitHub → Notion:** every `docs/todo/NN-*.md` whose Ship page exists adds a `- **Notion:** [<title>](<url>)` line to the header block (alongside Priority/Size/Status).
- When a file moves from `docs/todo/` to `docs/todo/done/`, update the `github-url` property to the new path in the same PR.
- Outreach/launch-ops Notion pages (LinkedIn drafts, 1:1 outreach, etc.) do **not** have docs/todo counterparts and are out of scope for cross-referencing.

## Backfilled so far (2026-04-26)

- Ship #43 ↔ `docs/todo/done/43-open-source-release.md`
- Ship #50 ↔ `docs/todo/50-anonymous-no-persist.md`

## Remaining

- [ ] Sweep the rest of the Notion DB for `Ship #NN`-titled pages (semantic search returned only #43 and #50, but pagination is unclear — verify by browsing the DB in the Notion UI). For each, set `github-url` and add `**Notion:**` to the matching markdown.
- [ ] Add a one-paragraph note to `CLAUDE.md` ("Backlog conventions" or similar) describing the cross-reference rule so future contributors keep it up.
- [ ] If a Ship page exists on Notion but no matching `docs/todo/NN-*.md` exists yet, create the markdown stub (don't leave the Notion page orphaned).

## Acceptance criteria

- Every "Ship #NN" Notion page has `github-url` set to a real path that resolves on `main`.
- Every active `docs/todo/NN-*.md` whose Ship page exists has a `**Notion:**` line in its header block.
- `CLAUDE.md` documents the convention so it's not just tribal knowledge.

## Not in scope

- Pulling Notion pages into the repo as YAML front-matter (over-engineering).
- Any tooling that auto-syncs status between the two systems (low ROI for two contributors).
- Outreach/marketing Notion pages.
