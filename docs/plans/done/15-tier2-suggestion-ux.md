# 15 — Tier 2 Suggestion Card UX

- **Priority:** P1
- **Size:** M (1–3 days) + S prerequisite (see below)
- **Source:** Reviewer feedback 2026-04 + `docs/reference/woo-redactietool-analyse.md`
- **Depends on:** #08 (Undo/redo — done), #13 (rule-based public-official filter) and #14 (structure heuristics) are recommended prerequisites but not hard blockers — the card's reason strings become more informative once those land
- **Blocks:** Name propagation work (future todo) — cannot propagate a classification that doesn't exist

> **Pivot note (2026-04):** This todo was written while the Tier 2 person verification ran through a local LLM. The LLM layer is now dormant (see `done/35-deactivate-llm.md`), so the card no longer receives role verdicts from the model. Instead, `subject_role` is set by the reviewer (three chips) and pre-filled by the rule engine in #13 (e.g. "voorafgegaan door 'wethouder' → publiek_functionaris"). Reason strings on the card now come from rule-based sources — structure heuristics (#14), function-title lookups (#13), and the Meertens name lookup (#12) — not from an LLM.

## Why

The Tier 2 suggestion card (`frontend/src/lib/components/review/Tier2Card.svelte`) has three concrete UX problems that a reviewer hits within the first minute of the review screen:

1. **Text disappears on "Lakken".** When a Tier 2 card is accepted, the card re-renders with the entity text still mounted inside a `<mark class="bg-warning/30">` — but because the card's background becomes green (`bg-green-50`) and the only status affordance is a tiny red "Gelakt" label, the reviewer reads the card as "empty white box". The mental model "this word will be blacked out on export" is invisible. There is also no per-card way to undo: the reviewer has to know to hit Ctrl+Z or scroll to the global undo button (and the global undo button only appears in Edit Mode, which this flow isn't).
2. **No reason picker on the card.** During manual redaction (`ManualRedactionForm.svelte`), the reviewer picks a Woo-grond from a grouped `<sl-select>`. On a Tier 2 card the article is whatever Deduce + the tier assigner pre-picked — usually `5.1.2e` — and there's no way to change it without rejecting the detection and re-drawing the selection manually. Reviewers will hit this the moment they see a name that should actually be redacted under `5.1.1d` (special personal data) instead of `5.1.2e`.
3. **"Classificatie nodig" is a dead end.** The card's reasoning text literally says *"Persoonsnaam gedetecteerd door NER. Classificatie nodig: burger, ambtenaar, of publiek functionaris."* — but there is no UI to perform the classification. This is not just a missing button: it's the central Tier 2 decision that the reviewer needs to make, and it has concrete downstream consequences (public officials must NOT be redacted — see CLAUDE.md §"Key design rules"). Post-pivot, the rule engine (#13) pre-fills `subject_role` whenever structure or a function-title lookup is confident, so the reviewer only has to decide in the genuinely ambiguous cases — but the chips must still be there for that decision.

None of this is covered by existing backlog items:
- #10 (Page Completeness Review) — per-page tracking, unrelated.
- #11 (Boundary Adjustment) — resizing existing bboxes, unrelated.
- #18 (Split and Merge Detections) — unrelated.
- #34 (Roles & Permissions) — auth roles, not subject classifications.

## Prerequisite (do first) — P1, S

**Add `subject_role` to the detection data model.** Without this the in-card classification UI cannot persist anything, and a reviewer who classifies someone as "publiek functionaris" loses that decision the moment they click away.

- [ ] Frontend `Detection` type gains optional `subject_role?: 'burger' | 'ambtenaar' | 'publiek_functionaris'` (`frontend/src/lib/types/index.ts`).
- [ ] `UpdateDetectionRequest` gains the same optional field (same file).
- [ ] Backend `Detection` ORM model + Pydantic schemas gain the same nullable column. New Alembic migration `add_subject_role_to_detections` (nullable, no default — pre-existing rows stay `NULL`).
- [ ] `PATCH /api/detections/{id}` accepts and persists `subject_role`. No cross-document propagation yet — that is a separate follow-up.
- [ ] Client-first check: `subject_role` is a *classification label*, not document content. Storing it on the server is fine. Do NOT simultaneously add `entity_text` — that would break #00.

This prerequisite is the only backend change in this todo. Everything below is frontend-only.

## Scope

### 1. Keep the redacted text visible on the card

- [ ] When `review_status` is `accepted` or `auto_accepted`, render the entity text with a **solid black background + white text** (visualizes "this will be blacked out on export") instead of the current white box.
- [ ] The rendered text must still come from the in-memory `entity_text` populated by `resolveEntityTexts()`. Do NOT fetch it from the server — there is none there.
- [ ] Replace the tiny red "Gelakt" label with a clearer state row: a `sl-badge variant="danger"` reading *"Gelakt"* plus an inline **"Ontlakken"** button (mirroring `Tier1Card.svelte`'s pattern — `onUnredact(detection.id)` wires through to the existing `onReject` handler in `DetectionList.svelte`).
- [ ] `rejected` status: keep current "Zichtbaar gehouden" treatment but also offer a "Toch lakken" button that re-runs the accept path. Same undo-stack command as the initial accept.
- [ ] `Tier2Card.svelte` must be able to emit `onReject` even when not pending — current code only wires the buttons inside the `isPending` branch. Extend the props if needed (no new props are required — `onAccept` / `onReject` are already passed).

### 2. In-card Woo-grond picker

- [ ] Add a compact `sl-select` to the card showing the current `woo_article`. Options = `Object.values(WOO_ARTICLES)` filtered to `tier === '2'` (same filter idea as `Tier3Panel.svelte` uses for its tier-3 list).
- [ ] Changing the article calls `detectionStore.review(id, { review_status, woo_article })` via a new handler `onChangeArticle(id, article)` on the card (wired through `DetectionList.svelte` to `+page.svelte`).
- [ ] The article change must go through the undo stack — create a new `ChangeArticleCommand` in `frontend/src/lib/stores/undo.svelte.ts` that captures `prevArticle` / `nextArticle` and calls `detectionStore.review` on forward/reverse. Alternative: extend `ReviewStatusCommand` to also capture article-only changes — pick whichever keeps the command class small.
- [ ] Recent-articles dropdown grouping from `ManualRedactionForm.svelte` is nice-to-have but not required here — the tier-2 list is short.

### 3. Role classification (burger / ambtenaar / publiek functionaris)

- [ ] Visible on the card only when `entity_type` is one that can belong to a person: `persoon`, `adres`, `telefoonnummer`, `email`. (Not `bsn`, `iban`, etc. — those are always personal data regardless of role.)
- [ ] UI: a three-button segmented control (Shoelace `sl-button-group` with three `sl-button` children, or three chips). Labels: *"Burger"*, *"Ambtenaar"*, *"Publiek functionaris"*.
- [ ] Clicking a chip sets `subject_role` via `detectionStore.review(id, { subject_role })`. Goes through the undo stack as a `SetSubjectRoleCommand` (or reuse the same command class as the article picker if the shape generalizes).
- [ ] **Publiek functionaris automatically rejects the redaction.** Per CLAUDE.md: *"Public officials (college B&W, raadsleden, etc.) should NOT be redacted."* The click is a single command that sets `subject_role = 'publiek_functionaris'` AND `review_status = 'rejected'`. Undo restores both.
- [ ] Reasoning text on the card should hide the "Classificatie nodig" sentence once `subject_role` is set — it's no longer needed.
- [ ] Pending detections without a classification show the three chips inline above the Lakken/Niet lakken row. The buttons remain usable without classifying — classification is *recommended*, not *required*. (Forcing it would block the existing one-click-accept flow.)

### 4. Small cleanups discovered along the way

- [ ] `Tier2Card.svelte` currently uses a `<p>` with an empty-ish `<mark>` when `entity_text` is missing (the `resolveEntityTexts` failure mode). Fall back to a visible *"— tekst niet beschikbaar —"* placeholder so broken extraction doesn't look like a rendering bug.
- [ ] When `isPropagated` is true, surface *which* earlier decision it was propagated from (if we can — otherwise keep the current line as-is).

## Acceptance criteria

- After clicking "Lakken" on a Tier 2 card, the entity text is still visible, styled as a black box with white text, and an "Ontlakken" button restores it.
- Reviewer can change a Tier 2 detection's Woo-grond directly on the card without rejecting and redrawing.
- Reviewer can classify a `persoon` (or equivalent) detection as burger / ambtenaar / publiek functionaris. The classification persists and survives a page reload.
- Classifying as publiek functionaris rejects the redaction in one click, with a single undo-stack entry that restores both the classification and the previous status.
- All new actions (accept, reject, ontlakken, change article, set role, publiek-functionaris-rejects) push commands onto the existing undo stack — Ctrl+Z works for all of them.
- Server never receives `entity_text`. Verified by network inspection on `PATCH /api/detections/{id}`.
- Tier2Card unit tests cover: accepted state renders visible text, role chip click dispatches correct command, publiek functionaris click rejects, article change dispatches.

## Not in scope

- **Cross-document / intra-document name propagation.** "Once I classify Jan Jansen as burger, apply to all occurrences" is a separate, larger todo. Create as a follow-up after this lands.
- **Per-dossier public officials reference list.** Mentioned in CLAUDE.md as a stripped-out feature to reintroduce later — that is its own todo, not this one.
- **Boundary adjustment on tier 2 cards.** Covered by #11.
- **Splitting a multi-word detection into multiple cards.** Covered by #18.
- **Forcing classification before accept.** Deliberately kept optional so the one-click-accept flow still works.

## Files likely to change

**Prerequisite (backend + types):**
- `backend/app/models/detection.py` (new `subject_role` column)
- `backend/app/schemas/detection.py` (Pydantic)
- `backend/alembic/versions/<new>_add_subject_role.py`
- `backend/app/api/detections.py` (accept field on PATCH)
- `frontend/src/lib/types/index.ts` (type + request type)
- `frontend/src/lib/api/client.ts` (no signature change — same `updateDetection`)

**Frontend UX:**
- `frontend/src/lib/components/review/Tier2Card.svelte` (primary)
- `frontend/src/lib/components/review/DetectionList.svelte` (new prop wiring)
- `frontend/src/routes/review/[docId]/+page.svelte` (new handler functions)
- `frontend/src/lib/stores/undo.svelte.ts` (new command class(es))
- `frontend/src/lib/stores/detections.svelte.ts` (no new actions — `review()` already handles partial updates)
