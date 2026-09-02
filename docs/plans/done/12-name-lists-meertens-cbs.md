# 12 — Name lists: Meertens voornamen + CBS achternamen

- **Priority:** P1
- **Size:** M (1–3 days)
- **Source:** `docs/reference/woo-redactietool-analyse.md` §"Wat zou een AI-taalmodel toevoegen?" and §"Voorstel: twee fasen" + pivot decision in `done/35-deactivate-llm.md`
- **Depends on:** #35 (dormant LLM — this todo is a partial replacement for the LLM person-role verification pass)
- **Blocks:** #13 (the rule engine uses these lists for its "is this actually a name?" check), #14 (structure heuristics cross-reference name lists)

## Why

Deduce is trained on medical records and routinely over-tags institution names, locations, and fragments as `persoon`. The LLM verification pass used to filter these out; with that pass dormant, we need a cheap, rule-based replacement. Name lists give us exactly that: a positive check ("the first token is a known Dutch first name") is a strong signal that a Deduce `persoon` hit is real, and the absence of any known first or last name is a strong signal that it is not.

The Nederlandse Voornamenbank (Meertens Instituut, KNAW) publishes `Top_eerste_voornamen_NL_2017.csv` as open data with one attribution requirement: mention the source and link to <https://www.meertens.knaw.nl/nvb>. We already have that in `THIRD_PARTY_LICENSES.md` (added in #35). The CBS achternamenbestand is public and unrestricted.

This is the single highest-value detection improvement post-pivot: it closes most of the false-positive gap left by deactivating the LLM, and it sharpens the true-positive signal for #13 and #14.

## Scope

### Data files

- [ ] Commit `backend/app/data/sources/Top_eerste_voornamen_NL_2017.csv` — the raw Meertens CSV, unmodified, so provenance is inspectable. Add a `README.md` in the same directory citing the source and the attribution requirement.
- [ ] Commit `backend/app/data/sources/cbs_achternamen.csv` — top N Dutch surnames from CBS. Pick a reasonable N (5k–10k); document the source URL in the same README.
- [ ] At application startup, normalize both files into fast lookup sets. Either:
  - (a) generate `backend/app/data/voornamen.json` / `achternamen.json` as a build step (compact, ~1 MB total), or
  - (b) load the CSVs at startup into in-memory sets and skip the JSON cache.
  - Pick (b) — simpler, avoids a build step, and the memory footprint is trivial.
- [ ] Normalization rules: lowercase, strip diacritics with `unicodedata.normalize("NFKD", ...)`, keep only the first column (the name itself) from Meertens, handle tussenvoegsels separately (see below).

### Tussenvoegsels list

- [ ] Hard-coded list of Dutch naamvoorvoegsels: `van`, `van den`, `van der`, `van de`, `van 't`, `de`, `der`, `den`, `ter`, `ten`, `te`, `het`, `'t`, `op`, `op den`, `op de`, `aan de`, `uit den`. Normalize the same way as the name lists (lowercased, no diacritics).
- [ ] A plausible Dutch surname may be a tussenvoegsel followed by a capitalized token ("Van den Berg"). The detector treats `Van den Berg` as a surname candidate even though `Van` alone is a tussenvoegsel, not a surname.

### Name engine module

- [ ] New `backend/app/services/name_engine.py` with three pure functions:
  - `load_name_lists() -> NameLists` — reads the CSVs once, returns a dataclass with `first_names: frozenset[str]`, `last_names: frozenset[str]`, `tussenvoegsels: frozenset[str]`. Called once at startup from `main.lifespan`, cached in `app.state.name_lists`.
  - `is_known_first_name(token: str, lists: NameLists) -> bool` — normalizes the token and looks it up.
  - `score_person_candidate(text: str, lists: NameLists) -> NameScore` — returns a dataclass with `has_known_first_name`, `has_known_last_name`, `first_name_index`, `last_name_index`, `is_plausible: bool`. `is_plausible` combines the signals with the existing `_is_plausible_person_name` heuristic in `ner_engine.py`.
- [ ] Unit tests covering: common names ("Jan de Vries" → plausible), org names that Deduce mis-tags ("Amsterdamse Hogeschool" → not plausible, existing heuristic still wins), tussenvoegsel-led surnames ("Van den Berg" → plausible), diacritics ("Gülnur Yılmaz" → plausible if her first name is in Meertens; falls through to the existing heuristic otherwise).

### Integration with `ner_engine.detect_tier2`

- [ ] When a Deduce `persoon` hit survives the existing `_is_plausible_person_name` filter, run it through `score_person_candidate`. Use the score to:
  - Drop the detection if neither a known first name nor a known last name appears in the span (raises the bar on the existing heuristic — only fires when the span looks like a name structurally AND nothing is recognized).
  - **Boost confidence** by +0.10 when a known first name is present, additional +0.05 when a known last name is also present. Cap at 0.95. This is the signal the Tier 2 card UX (#15) surfaces as "voornaam op Meertens-lijst".
- [ ] Surface the score in `NERDetection.reasoning` so `Tier2Card.svelte` can display the rule that fired: *"Voornaam herkend in Nederlandse Voornamenbank (Meertens Instituut)."* This is also where the attribution link lands in the UI — `Tier2Card.svelte` should render "Meertens Instituut" as a link to <https://www.meertens.knaw.nl/nvb> whenever this reason is shown.

### Confidence in the pipeline

- [ ] `llm_engine.run_pipeline` no longer handles confidence boosting for Deduce hits when names match Tier 1 — that logic moves to the name engine (name-list match is strictly stronger than "both Tier 1 and Tier 2 found the same thing"). Keep the existing tier1/tier2 cross-boost as a fallback.

## Acceptance criteria

- `backend/app/data/sources/` contains both raw CSVs with a README citing Meertens + CBS.
- Startup loads the lists once (~<100 ms) and caches them on `app.state`.
- `test_name_engine.py` covers the normalization, lookup, and scoring paths with fixtures for real Dutch names, org names, tussenvoegsel-led surnames, and diacritic-bearing names.
- A previously-noisy test document (e.g. one of the existing fixtures under `test/generated-fixtures`) produces measurably fewer `persoon` false positives with the name engine enabled. Record the before/after counts in the PR description so the regression from #35 is visibly closed.
- Detection reasoning on the Tier 2 card shows "Voornaam herkend in Nederlandse Voornamenbank (Meertens Instituut)" with a link to <https://www.meertens.knaw.nl/nvb> when the name engine contributed the positive signal.
- `THIRD_PARTY_LICENSES.md` already lists Meertens — verify the link is live and the attribution language matches what's displayed in the UI.

## Not in scope

- Matching against public-official lists — that is #13. This todo only deals with "is this a plausible private-person name".
- Per-document custom wordlists — that is #21.
- Fuzzy matching for typos, inflection, or historical spellings. Exact normalized match only.
- Frontend changes beyond the reason-string link. The full card redesign lives in #15.

## Files likely to change

- `backend/app/data/sources/Top_eerste_voornamen_NL_2017.csv` (new)
- `backend/app/data/sources/cbs_achternamen.csv` (new)
- `backend/app/data/sources/README.md` (new)
- `backend/app/services/name_engine.py` (new)
- `backend/app/services/ner_engine.py` (integration)
- `backend/app/services/llm_engine.py` (confidence boosting cleanup)
- `backend/app/main.py` (lifespan: load lists once)
- `backend/tests/test_name_engine.py` (new)
- `backend/tests/test_ner_engine.py` (regression fixtures)
- `THIRD_PARTY_LICENSES.md` (verify attribution wording)
- `frontend/src/lib/components/review/Tier2Card.svelte` (link in reason string — merge with #15 if timing overlaps)
