# `app/llm/` — Dormant LLM layer

**Status: dormant.** Nothing in the live request path imports this module.
The detection pipeline in `app/services/llm_engine.py` runs Tier 1 (regex)
and Tier 2 (Deduce NER + heuristics) without calling any LLM. This directory
is kept in-tree as a parked revival path.

## Why it's here

The April 2026 pivot (see `docs/reference/woo-redactietool-analyse.md` and
todo `docs/todo/done/35-deactivate-llm.md`) removed the Ollama/Gemma
verification pass from the default pipeline. The rationale is the
CISO-friendly story: no model hosting, no GPU, no "we promise we don't send
your documents anywhere" footnote. Detection becomes rules + wordlists, and
the trust story becomes one sentence: *geen taalmodel in het actieve pad*.

The code was not deleted because:

1. **Re-enabling is a one-line change.** `settings.llm_tier2_enabled=True`
   restores the original behavior for experimentation branches without a
   revert.
2. **The abstract interface and dataclasses in `provider.py` are useful
   reference** for whatever rule-based replacement lands in todos #12–#17.
3. **Phase 2 (browser-only LLM via WebGPU)** — when it becomes feasible —
   will reuse the same `LLMProvider` shape.

## How to revive it

1. Set `LLM_TIER2_ENABLED=true` (or `LLM_TIER3_ENABLED=true`) in `.env`.
2. Start Ollama locally (`ollama serve`) and pull a model
   (`ollama pull gemma4:26b`).
3. `services/llm_engine.run_pipeline` will then lazy-import
   `app.llm.get_llm_provider` and run the person-role verification pass.

Nothing in the live production path should import from this directory.
`services/llm_engine.py` only imports `app.llm.provider` (the abstract
interface, no side effects); the concrete Ollama client is imported inside
the verification branch, which the dormant flag keeps unreachable.

## Files

- `provider.py` — abstract `LLMProvider` + `RoleClassification` /
  `ContentAnalysisResult` dataclasses. Import-safe.
- `ollama.py` — local Ollama implementation. **Do not import** from live
  code — only via the factory in `__init__.py`, which itself is only called
  from the dormant branch of `services/llm_engine.py`.
- `prompts.py` — Dutch prompt templates for role classification and content
  analysis. Reference only while dormant.
- `__init__.py` — provider factory (singleton).

## See also

- `docs/reference/woo-redactietool-analyse.md` — the analysis that motivated
  the pivot.
- `docs/todo/done/35-deactivate-llm.md` — the todo that performed this
  deactivation.
- Todos #12–#17 — the rule-based replacements that close the detection gap
  the dormant LLM used to cover.
