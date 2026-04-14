# 17 — Publieke functionarissen referentielijst (per-document)

- **Priority:** P2
- **Size:** M (1–3 days)
- **Source:** `docs/reference/woo-redactietool-analyse.md` §"Wat moet er zwartgelakt worden?" (Categorie 2) + `CLAUDE.md` §"Key design rules" (reintroduce the per-dossier reference-list UI that was stripped during simplification)
- **Depends on:** #13 (functietitel rule engine — this todo's lookup is a stronger override than title matching), #15 (Tier 2 card UX — the card is where a reviewer *uses* the list)
- **Blocks:** Nothing

## Why

The rule engine in #13 catches `wethouder Jan de Vries` by matching on the function title that sits in front of the name. But in real Woo-documenten, names of public officials routinely appear *without* their title — in a cc line, a body paragraph, a minute, or a table. A reviewer who already knows "this dossier is about the college van B&W of gemeente Utrecht" wants to **once** seed the list of officials for that dossier, and have every subsequent mention of those names (with or without a title) auto-rejected.

This is the part of public-official handling that cannot be solved by generic rules: the membership of "college van B&W" is local, changes per dossier, and there is no authoritative national CSV we can ship with the app. The per-document list is the reviewer's escape hatch for "my rules don't know about these people, but I do."

The earlier prototype had this feature; it was stripped during simplification (see `CLAUDE.md` §"Key design rules" — *"The per-dossier reference-list UI was stripped during simplification; reintroduce as part of a future todo."*). This todo is that follow-up, now in its pivot-aware form: the list is per-**document** (the app is single-document today), lives in IndexedDB first (client-first), and the server only learns about it as a flat list of normalized name strings scoped to the document.

## Scope

### Data model

- [ ] New table `document_reference_names`:
  - `id`, `document_id` (FK to `documents`), `normalized_name` (lowercased, diacritics stripped, tussenvoegsels kept), `display_name` (what the reviewer typed), `role_hint` (`publiek_functionaris` default; future values `ambtenaar`, `burger`), `created_at`.
  - No `entity_text` from the PDF. Only the reviewer-provided string — which is a *label*, not document content.
- [ ] Alembic migration adds the table with a composite unique index on `(document_id, normalized_name)`.
- [ ] IndexedDB mirror: `referenceNames` store keyed by `documentId` → `Array<{display, normalized, role_hint}>`. Writes go to IndexedDB first, then sync to server (same pattern as manual detections in `detections.svelte.ts`).

### API

- [ ] `GET /api/documents/{id}/reference-names` → list
- [ ] `POST /api/documents/{id}/reference-names` → add one; body `{display_name, role_hint}`; server normalizes
- [ ] `DELETE /api/documents/{id}/reference-names/{name_id}` → remove
- [ ] No bulk endpoint in v1; the UI adds names one at a time

### Pipeline integration

- [ ] `llm_engine.run_pipeline` already accepts `public_official_names: list[str] | None` (legacy parameter from the LLM era). Rewire `AnalyzeRequest` so the frontend sends the current document's reference-name list on every analyze call. The list is short (typically <20 entries); no caching needed.
- [ ] The name engine from #12 does the actual matching: a Deduce `persoon` detection whose normalized span matches any reference name is marked `review_status="rejected"`, `subject_role="publiek_functionaris"`, `reasoning="Naam op publiek-functionarissenlijst van dit document."`, `source="reference_list"`.
- [ ] Ordering: **reference list beats function-title rule engine (#13) beats name-list scoring (#12)**. The most specific signal wins.

### Frontend UI

- [ ] New panel on the review screen, collapsed by default, labeled *"Publiek functionarissen"* with a count badge. Sits under the detection list or in a new "Document instellingen" accordion — pick whichever doesn't crowd the sidebar.
- [ ] Panel contents: an `sl-input` for adding a name, a list of current names with a trash icon each, and a one-liner explanation: *"Namen van personen die niet gelakt hoeven te worden (bijv. college B&W). Geldt alleen voor dit document."*
- [ ] Adding a name triggers re-analysis: the frontend calls `/api/analyze` again with the updated list. Newly-matched detections flip to `rejected` in place; the reviewer sees the pending queue shrink.
- [ ] Removing a name also triggers re-analysis — previously-rejected detections by that reference flip back to `pending`.
- [ ] Undo stack: add/remove reference name commands go through the same undo stack as detection changes (`AddReferenceNameCommand`, `RemoveReferenceNameCommand`).

### Tests

- [ ] `tests/test_reference_names.py`: POST adds a name, GET returns it, DELETE removes it, normalization is consistent ("De Vries" == "de vries").
- [ ] `tests/test_llm_engine.py`: a fixture where "Jan Jansen" is on the reference list and appears twice in the body — both detections come back as `rejected` with source `reference_list`.
- [ ] Frontend: a component test for the panel's add/remove flow.

## Acceptance criteria

- Reviewer can add "Jan de Vries" to a document's reference list and every Tier 2 `persoon` detection matching that name flips to `rejected` in the next analysis pass.
- The list persists across page reloads (IndexedDB + server round-trip).
- Removing a name un-rejects the matching detections.
- Undo restores both adds and removes.
- No `entity_text` ends up on the server — only the reviewer-provided display name, which is a label, not extracted content.
- Typing "de Vries" and later seeing "De Vries" in a document produces a match (normalization works).

## Not in scope

- **Cross-document propagation.** "Remember Jan de Vries as a publiek functionaris for every document in this workspace" is a bigger change that needs auth + organizations (#32, #33). Per-document only for now.
- **Importing a list from CSV / LinkedIn / an external register.** Paste-from-clipboard is a P3 follow-up.
- **Negative list** ("these people ARE burgers, always redact them"). Not needed — the default is redact, reference list is the opt-out.
- **Fuzzy matching beyond normalization.** Exact normalized match only. Typos are the reviewer's responsibility.

## Files likely to change

- `backend/app/models/reference_name.py` (new)
- `backend/alembic/versions/<new>_add_reference_names.py`
- `backend/app/api/reference_names.py` (new)
- `backend/app/api/analyze.py` (wire up `public_official_names` from request)
- `backend/app/services/name_engine.py` (reference-list match path)
- `backend/app/services/llm_engine.py` (ordering)
- `backend/tests/test_reference_names.py` (new)
- `frontend/src/lib/stores/reference-names.svelte.ts` (new)
- `frontend/src/lib/components/review/ReferenceNamesPanel.svelte` (new)
- `frontend/src/routes/review/[docId]/+page.svelte` (mount panel, pass list to analyze)
- `frontend/src/lib/api/client.ts` (new CRUD calls)
- `frontend/src/lib/stores/undo.svelte.ts` (new command classes)
