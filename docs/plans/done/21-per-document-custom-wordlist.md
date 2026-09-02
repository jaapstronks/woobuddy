# 21 — Per-document custom wordlist ("eigen zoektermen")

- **Priority:** P2
- **Size:** S (< 1 day)
- **Source:** `docs/reference/woo-redactietool-analyse.md` §"Eigen zoektermen per document"
- **Depends on:** #09 (Search-and-redact — done), #17 (reference-name panel pattern — same storage + UX shape)
- **Blocks:** Nothing

## Why

The analyse.md makes a small but important observation: reviewers routinely know *things about the document* that no rule engine will ever know. A bedrijfsnaam of a klokkenluider, a straatnaam that identifies a specific complaint, the codename of an intern project — the reviewer reads the dossier brief once, recognizes three or four terms that need to be blacked out throughout, and wants to tell the tool *"these strings are sensitive for this document only"*.

This is functionally "search-and-redact, but saved and re-applied on every analyze pass". The existing search feature (#09) is one-shot: the reviewer types a term, the matches get redacted, end of transaction. A custom wordlist is persistent: the terms survive a page reload, they're re-applied the next time the document is analyzed, and they show up in the redaction log as `source="custom_wordlist"` instead of `source="search"`.

Pairs naturally with #17 (publieke functionarissen reference list): both are per-document, both are reviewer-provided labels, both trump the generic detection pipeline. Different intent (one is opt-out, one is opt-in) so they deserve separate UI, but they share storage and API shape.

## Scope

### Data model

- [ ] New table `document_custom_terms`:
  - `id`, `document_id` (FK), `term` (raw reviewer input, UTF-8, max 200 chars), `normalized_term` (lowercased, whitespace-collapsed, diacritics preserved — unlike the name engine, terms are matched case-insensitively but otherwise verbatim), `match_mode` (`exact` default, future `prefix` / `whole_word`), `woo_article` (what article to tag the match with — default `5.1.2e`), `created_at`.
  - Composite unique index on `(document_id, normalized_term, match_mode)`.
  - **Terms are labels, not document content.** The reviewer typed them. Storing them is client-first compliant.
- [ ] Alembic migration.
- [ ] IndexedDB mirror: `customTerms` store keyed by `documentId`. Same write-IDB-first pattern as #17.

### API

- [ ] `GET /api/documents/{id}/custom-terms`
- [ ] `POST /api/documents/{id}/custom-terms` — body `{term, match_mode?, woo_article?}`
- [ ] `DELETE /api/documents/{id}/custom-terms/{term_id}`
- [ ] No bulk endpoint in v1.

### Matcher integration

- [ ] New module `backend/app/services/custom_term_matcher.py`:
  - `match_custom_terms(text: str, terms: list[CustomTerm]) -> list[TermMatch]` — returns character offsets for every occurrence. Exact mode is a case-insensitive substring scan; `prefix` and `whole_word` are reserved for later.
  - For performance: pre-compile each term once per analyze call. With <50 terms this is trivial.
- [ ] `llm_engine.run_pipeline` grows a `custom_terms: list[CustomTerm] | None` parameter. When set, the matcher runs after Tier 1 but before structure/name engines. Each match produces a fresh `Detection` with:
  - `entity_type="custom"`, `tier="2"`, `review_status="accepted"` (custom terms are opt-in; the reviewer already made the decision by typing them), `source="custom_wordlist"`, `woo_article` from the term, `reasoning=f"Zoekterm '{term}' uit documentspecifieke lijst."`.
- [ ] De-duplication: if a custom-term match overlaps with a Tier 1 or Tier 2 detection, the custom term's Woo-artikel wins (most specific reviewer intent), but the bbox is the union — the reviewer's term is at least as restrictive.

### Frontend UI

- [ ] New panel in the review sidebar, sibling to the reference-name panel from #17, labeled *"Eigen zoektermen"* with a count badge.
- [ ] Panel contents: `sl-input` for adding, optional Woo-artikel `sl-select` (defaults to `5.1.2e`), list of current terms each with match count (*"'NL-Alert' — 4 gevonden"*) and a trash icon.
- [ ] Adding a term triggers re-analysis (same as #17). The match count updates when analysis completes.
- [ ] Removing a term also triggers re-analysis — the corresponding `custom` detections disappear.
- [ ] Undo stack: `AddCustomTermCommand`, `RemoveCustomTermCommand`.
- [ ] Accessibility: the input accepts Enter to submit, and the panel is reachable with Tab from the detection list.

### Tests

- [ ] `tests/test_custom_term_matcher.py`: exact match, case insensitivity, multi-word term, overlapping matches, term that's a substring of a longer word (must still match in exact mode).
- [ ] `tests/test_llm_engine.py`: a fixture with a custom term "Project Apollo" produces two `custom` detections with the right Woo-artikel.
- [ ] API round-trip test.

## Acceptance criteria

- Reviewer can add "Project Apollo" to the custom wordlist and every occurrence in the document becomes a `custom` detection with `review_status="accepted"` and the right Woo-artikel.
- The list persists across page reloads.
- Removing a term removes its detections on the next analysis pass.
- Custom-term detections show up in the redaction log (#19) with `source="custom_wordlist"` so oversight can see *why* a passage was redacted.
- Undo restores adds and removes.
- Custom terms never introduce `entity_text` onto the server — only the reviewer-typed term, which is a label.

## Not in scope

- **Regex terms.** Reviewers aren't engineers. Exact substring match only.
- **Bulk import from CSV.** Paste-from-clipboard is a P3 follow-up.
- **Fuzzy matching or typo tolerance.** Reviewer's responsibility to spell the term.
- **Whole-word / prefix modes.** Reserved in the schema, not implemented in v1.
- **Cross-document wordlist.** Per-document only — the same reason as #17.
- **Term suggestions from the document body.** A nice P3: show the reviewer the most frequent capitalized bigrams as suggestions. Out of scope now.

## Files likely to change

- `backend/app/models/custom_term.py` (new)
- `backend/alembic/versions/<new>_add_custom_terms.py`
- `backend/app/api/custom_terms.py` (new)
- `backend/app/services/custom_term_matcher.py` (new)
- `backend/app/services/llm_engine.py` (integration)
- `backend/app/api/analyze.py` (pass custom terms into the pipeline)
- `backend/tests/test_custom_term_matcher.py` (new)
- `backend/tests/test_llm_engine.py` (regression)
- `frontend/src/lib/stores/custom-terms.svelte.ts` (new)
- `frontend/src/lib/components/review/CustomTermsPanel.svelte` (new)
- `frontend/src/routes/review/[docId]/+page.svelte` (mount panel, pass list to analyze)
- `frontend/src/lib/api/client.ts` (CRUD)
- `frontend/src/lib/stores/undo.svelte.ts` (command classes)
