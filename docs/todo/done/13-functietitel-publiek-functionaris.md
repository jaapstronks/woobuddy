# 13 — Functietitel + publiek-functionaris rule engine

- **Priority:** P1
- **Size:** M (1–3 days)
- **Source:** `docs/reference/woo-redactietool-analyse.md` §"Wat moet er zwartgelakt worden?" (Categorie 1) + pivot decision in `done/35-deactivate-llm.md`
- **Depends on:** #35 (LLM deactivated), #12 (name lists — needed to anchor "which token is the name")
- **Blocks:** #15 final UX — the Tier 2 card needs a non-empty reason when pre-filling `subject_role`

## Why

When the LLM was on, `persoon` detections that the model recognized as a public official acting in capacity were auto-marked `rejected` (don't redact). With the LLM off, those names now sit in the reviewer's pending queue and require manual confirmation for every single wethouder, raadslid, and burgemeester in a document. This is exactly the repetitive work the analyse.md promises we can eliminate with rules.

The rule: **a person name preceded (within a small window) by a Dutch function title is almost certainly that person in that role.** If the title is a *publiek-functionaris* title, the detection should default to `rejected` (the public-officials-do-not-redact rule from CLAUDE.md). If it's a *civil-servant* title, the detection stays `pending` but with a pre-filled `subject_role = 'ambtenaar'` so the reviewer only has to confirm.

This todo builds that rule engine as a small, pure module with two lookup lists — no ML involved.

## Scope

### Data: two function-title lists

- [ ] `backend/app/data/functietitels_publiek.txt` — titles whose bearer is a *publiek functionaris* acting in an official capacity. Seed list:
  - `burgemeester`, `loco-burgemeester`, `wethouder`, `gedeputeerde`, `commissaris van de koning`, `minister`, `staatssecretaris`, `kamervoorzitter`, `fractievoorzitter` (only in council context), `raadslid`, `statenlid`, `gemeenteraadslid`, `provinciale statenlid`, `dijkgraaf`, `heemraad`, `waterschapsbestuurder`, `college van b&w`, `college van burgemeester en wethouders`, `gemeentesecretaris`, `griffier`, `rechter`, `officier van justitie`, `advocaat-generaal`, `procureur-generaal`.
- [ ] `backend/app/data/functietitels_ambtenaar.txt` — titles that indicate civil-servant status but do NOT qualify as "public official acting in capacity". Seed list:
  - `beleidsmedewerker`, `beleidsadviseur`, `juridisch adviseur`, `juridisch medewerker`, `teamleider`, `teamleider handhaving`, `handhaver`, `toezichthouder`, `inspecteur`, `projectleider`, `programmamanager`, `directeur` (context-dependent — see edge case below), `afdelingshoofd`, `strateeg`, `communicatieadviseur`, `woordvoerder`, `secretaresse`, `managementassistent`.
- [ ] Both lists ship as UTF-8 text files, one title per line, comments start with `#`. Hand-curated; no external source. Document the curation decisions in a comment block at the top.

### Rule engine module

- [ ] New `backend/app/services/role_engine.py` with:
  - `FunctionTitleLists` dataclass (loaded once at startup, cached on `app.state`).
  - `find_function_title_near(full_text: str, span_start: int, span_end: int, lists: FunctionTitleLists, window: int = 40) -> FunctionTitleMatch | None` — looks at `window` characters before and after the detection span (not including the span itself) for any title on either list. Match is case-insensitive, whole-word (use `\b`).
  - `FunctionTitleMatch` carries: matched title, which list (`publiek` | `ambtenaar`), offset from span, proximity (tokens between).
- [ ] Tie-breaking rules:
  - Before-context beats after-context (titles usually precede names: "wethouder Jan de Vries" — the title is what gives you the role).
  - Publiek list beats ambtenaar list if both would match.
  - If a hit is >= 6 tokens away from the span, ignore it (too loose).

### Integration with the pipeline

- [ ] `llm_engine.run_pipeline` grows a **rule-based role classifier pass** that runs after NER detection and before result assembly. For each Tier 2 `persoon` detection:
  - Call `find_function_title_near` against the full text at the detection's `start_char`/`end_char`.
  - If a publiek match fires: set `review_status="rejected"`, `subject_role="publiek_functionaris"`, `reasoning=f"Publiek functionaris: voorafgegaan door '{title}' in de brontekst."`, `source="rule"`.
  - If an ambtenaar match fires: keep `review_status="pending"`, set `subject_role="ambtenaar"`, `reasoning=f"Vermoedelijk ambtenaar in functie: voorafgegaan door '{title}'."`, `source="rule"`.
  - If neither fires: existing pending-with-Deduce-reasoning branch.
- [ ] This pass replaces the dormant LLM verification branch in `run_pipeline` for the common case. The lazy-import block stays in place for the revival path.
- [ ] `public_official_names` parameter still short-circuits to `rejected` before the rule engine runs — an explicit per-document list (coming in #17) trumps generic function-title matching.

### Tests

- [ ] `tests/test_role_engine.py`:
  - "Wethouder Jan de Vries" → publiek, rejected.
  - "wethouder Jan de Vries" (lowercased) → publiek, rejected.
  - "beleidsmedewerker Jan de Vries" → ambtenaar, pending.
  - "Jan de Vries, wethouder van Utrecht" (title after name) → publiek, rejected (after-context path).
  - "Jan de Vries zei dat de wethouder gebeld had" → no match (title too far / different person).
  - "Jan de Vries" standalone → no match.
- [ ] Regression: re-run an existing fixture that had LLM-driven `rejected` outcomes and verify the rule engine reproduces them for the common cases.

### CLAUDE.md update

- [ ] Add a one-line pointer in the "Key design rules" section: "Public-official detection is rule-based (#13). Titles are matched against `backend/app/data/functietitels_publiek.txt` — edit the list, not the code, to extend coverage."

## Acceptance criteria

- Running the pipeline on a test document containing "Wethouder Jan de Vries" produces a Tier 2 `persoon` detection with `review_status="rejected"`, `subject_role="publiek_functionaris"`, and a reason string naming the matched title.
- No LLM calls — the dormant path is not touched.
- Function-title lists are editable without code changes. A new title added to `functietitels_publiek.txt` is picked up on restart.
- `test_role_engine.py` covers the six cases above.
- The regression from #35 is visibly narrowed: a fixture that previously generated N `pending` person cards post-#35 now generates materially fewer after #12 and #13 land.

## Not in scope

- Multilingual function titles. Dutch only.
- Fuzzy matching / stemming. Whole-word exact match.
- Overriding a rule match from the UI in a way that writes back to the list. Reviewers override per-detection via the Tier 2 card; the list stays stable.
- Per-document custom function-title lists. #17 introduces the per-document *names* list; a per-document *titles* list would be a separate enhancement.

## Files likely to change

- `backend/app/data/functietitels_publiek.txt` (new)
- `backend/app/data/functietitels_ambtenaar.txt` (new)
- `backend/app/services/role_engine.py` (new)
- `backend/app/services/llm_engine.py` (integration)
- `backend/app/main.py` (startup load)
- `backend/tests/test_role_engine.py` (new)
- `CLAUDE.md` (one-line pointer)
