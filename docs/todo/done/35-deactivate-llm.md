# 35 — Deactivate LLM layer (dormant)

- **Priority:** P0
- **Size:** S (< 1 day)
- **Source:** `docs/reference/woo-redactietool-analyse.md`
- **Depends on:** —
- **Blocks:** #12 (Meertens/CBS name lists), #13 (functietitel + publiek-functionaris rule engine), #14 (structuurherkenning), #15 (Tier 2 card UX), #16 (Tier 1 gaps), #17 (publieke functionarissen referentielijst), #20 (bulk sweeps), #21 (per-document wordlist)

## Why

The WOO redactietool analysis (`docs/reference/woo-redactietool-analyse.md`) argues that a regex + wordlist + structure-heuristic tool without an LLM is **more sellable, simpler to deploy, and covers 70–80% of the detection need** — which is the saaiste, meest repetitieve deel of the work. The remaining 10–15% that an LLM would add sits in a grey zone a reviewer has to verify anyway, and the 10–15% that is genuinely hard (persoonlijke beleidsopvattingen, strategische afwegingen) is mensenwerk regardless of model quality.

The privacy pitch also becomes one sentence: *uw documenten verlaten nooit uw infrastructuur en er komt geen taalmodel aan te pas*. No GPU, no model hosting, no verwerkersovereenkomst for a model provider, no DPIA for content routing.

This todo **deactivates** the LLM in the live pipeline but **keeps the code in-tree** as a parked revival path. Flipping the flag re-enables the original behavior for experimentation branches.

## Scope (as implemented)

### Backend code

- [x] `backend/app/config.py`: add `llm_tier2_enabled: bool = False` and `llm_tier3_enabled: bool = False` settings. Document the flags as revival-only.
- [x] `backend/app/services/llm_engine.py`: change `run_pipeline`'s `use_llm_verification` parameter to `bool | None`, defaulting to `None`, which reads `settings.llm_tier2_enabled`. Move `from app.llm import get_llm_provider` to a lazy import inside the verification branch so the dormant path never touches `app.llm.ollama`. Keep the `LLMProvider`/`RoleClassification` type imports at module level (they're side-effect-free, from `app.llm.provider`).
- [x] `backend/app/main.py`: `_probe_llm_status` now short-circuits to `"disabled"` when both flags are false, without importing the provider. Health endpoint returns `{"llm": <status>, "ollama": <status>}` where `ollama` is kept as a legacy alias.
- [x] `backend/app/llm/README.md`: new file explaining the layer is dormant, why it's kept in-tree, how to revive it.
- [x] Tests: `test_llm_verification.py` now passes `use_llm_verification=True` explicitly (the revival path) and patches `app.llm.get_llm_provider` instead of `app.services.llm_engine.get_llm_provider`. New test in `test_llm_engine.py` asserts the default pipeline does not import `app.llm.ollama`.

### Documentation

- [x] `CLAUDE.md`: Tier 1/2/3 block rewritten. Tier 2 lists the regex+rule stack; Tier 3 is "reserved, no LLM in active pipeline". Architecture bullet drops "Ollama + Gemma 4". Backend conventions drop the LLM provider bullet and warn against importing from `app.llm.*` in new code.
- [x] `README.md`: privacy paragraph rewritten with the "geen taalmodel aan te pas" one-liner; Ollama install step removed from the Mac setup; techstack bullet for "LLM: Gemma 4" replaced with a dormant-path note.
- [x] `.env.example`: Ollama variables marked as revival-only; new `LLM_TIER2_ENABLED` / `LLM_TIER3_ENABLED` flags, both defaulting to false.
- [x] `THIRD_PARTY_LICENSES.md`: Gemma 4 row moved under a "dormant" subheading; Meertens Voornamenbank attribution added in anticipation of #12.
- [x] `docs/todo/README.md`: philosophy bullet #4 rewritten (no more "the one unavoidable server touchpoint for content"); new bullet #1 makes the no-LLM stance explicit; Phase B gets todos #12–#17 (pivot work renumbered to the lowest available slots), Phase C gets #19 (redaction log, promoted), #20 (bulk sweeps), #21 (per-document wordlist); "Briefings Not Adopted" section documents the Tier 2 and Tier 3 LLM deactivation.
- [x] `docs/todo/WOO_BUDDY_TODO.md`: moved to `docs/todo/done/WOO_BUDDY_TODO.md` with a "HISTORICAL — dormant LLM setup" banner at the top. Nobody should need to install Ollama to run the app.
- [x] `docs/todo/15-tier2-suggestion-ux.md`: pivot note added to the frontmatter explaining that `subject_role` and reason strings now come from the rule engine, not an LLM verdict.
- [x] `docs/todo/19-redaction-log.md`: frontmatter promoted to P1, Phase C; pivot note added explaining why (analyse.md identifies audit trail as the headline sales feature).

### Not touched

- `backend/app/llm/*.py` other than the new README — the code is deliberately kept intact.
- `backend/app/llm/prompts.py` — reference material for revival, no change.
- Frontend — the health banner still reads `ollama` via the legacy alias; no breakage. A dedicated frontend cleanup pass can come later if the banner starts feeling vestigial.
- Tests that pass `use_llm_verification=False` explicitly — they already have stable behavior and were left as-is.

## Behavioral impact

**Regression to be aware of:** with the LLM off, Deduce `persoon` detections that were previously either dropped (role=`not_a_person`) or auto-marked `rejected` (role=`public_official`) now surface as `pending` and sit in the reviewer's confirmation queue. That's the exact gap todos #12–#14 close:

- **#12** adds Meertens voornamen / CBS achternamen lookups so Deduce's false positives get dropped by a cheap positive-name check.
- **#13** adds a function-title + publiek-functionaris rule engine so "wethouder Jan de Vries" gets the same `rejected` suggestion the LLM used to produce.
- **#14** adds structure detection (e-mailheaders, handtekeningblokken, aanhef) so names in a signature block get higher confidence and auto-accept without reviewer intervention.

Until those land, expect a noisier review queue. This is acceptable for a pre-pilot prototype with no production users.

## Acceptance criteria (all met)

- [x] Default `run_pipeline` call does not import `app.llm.ollama` — enforced by `test_default_pipeline_does_not_import_ollama_provider`.
- [x] Full backend test suite passes (`pytest` → 81 passed).
- [x] Ruff lint passes on touched files.
- [x] Health endpoint returns `{"llm": "disabled", "ollama": "disabled"}` out of the box.
- [x] Flipping `LLM_TIER2_ENABLED=true` restores the original pipeline behavior, verified by the existing `test_llm_verification.py` suite (which now passes `use_llm_verification=True` explicitly).
- [x] `CLAUDE.md`, `README.md`, `.env.example`, and the todo index reflect the new stance consistently. No stray "Ollama required" instructions in the live docs.

## Files changed

- `backend/app/config.py`
- `backend/app/main.py`
- `backend/app/services/llm_engine.py`
- `backend/app/llm/README.md` (new)
- `backend/tests/test_llm_engine.py`
- `backend/tests/test_llm_verification.py`
- `CLAUDE.md`
- `README.md`
- `THIRD_PARTY_LICENSES.md`
- `.env.example`
- `docs/todo/README.md`
- `docs/todo/15-tier2-suggestion-ux.md`
- `docs/todo/19-redaction-log.md`
- `docs/todo/done/WOO_BUDDY_TODO.md` (moved from `docs/todo/`)
- `docs/todo/done/35-deactivate-llm.md` (new — this file)
- `docs/todo/12-name-lists-meertens-cbs.md` (new)
- `docs/todo/13-functietitel-publiek-functionaris.md` (new)
- `docs/todo/14-structuurherkenning.md` (new)
- `docs/todo/16-tier1-gaps.md` (new)
- `docs/todo/17-publieke-functionarissen-referentielijst.md` (new)
- `docs/todo/20-bulk-sweep-flows.md` (new)
- `docs/todo/21-per-document-custom-wordlist.md` (new)
- (Phase B existing todos renumbered downward so the lowest numbers reflect the pivot's highest-priority work: #34 → #15, #12 → #18; Phase C/D/E/F/G items shifted accordingly — full map in the PR description.)
