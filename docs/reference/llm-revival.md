# Reviving a local LLM pass (future reference)

**Status:** not implemented. This document exists so a future contributor
can re-add a local LLM verification pass without having to re-derive the
design from scratch. There is no dormant code in the tree to flip on — the
LLM layer was fully removed in April 2026. If you want it back, you are
adding new code, not un-commenting old code.

## Scope: local only

If we ever reintroduce an LLM step, it must be **local-only**. Document
text may not leave the operator's machine (or, for the hosted tier, our
NL-hosted infrastructure). That rules out OpenAI, Anthropic, Google
Vertex, Azure OpenAI, Mistral hosted, and every other SaaS inference
provider.

The preferred stack is:

- **[Ollama](https://ollama.com)** as the runtime. Single binary, CPU or
  GPU, stable HTTP API on `localhost:11434`, supports tool-calling on
  recent models.
- **Google Gemma** (e.g. `gemma3:27b-instruct` or whatever the current
  best open-weights Gemma is when you read this) as the default model.
  Gemma is small enough to fit in a reasonable dev box and good enough
  at Dutch for the role-classification task the old pipeline used.
- Other local options are fine if they implement the Ollama API:
  `llama.cpp` with the OpenAI-compatible shim, `vLLM`, `LM Studio`, etc.
  Pick whatever the operator already has running.

Do not introduce any dependency that phones home for weights, telemetry,
or activation. Do not add a "cloud fallback" toggle.

## Why we removed it

Pre-2026 the pipeline ran a Tier 2 verification pass: every Deduce
`persoon` detection was sent to Ollama + Gemma with surrounding context,
the model returned a role classification (`citizen`, `civil_servant`,
`public_official`) and a `should_redact` boolean, and the pipeline used
that to flip `review_status` between `pending` and `rejected`.

It worked but it was the wrong trade-off:

1. **Trust story.** "Uw PDF verlaat nooit uw browser" is undermined the
   moment the server calls an LLM — even a local one, the CISO has to
   verify the claim every time.
2. **Cost model.** Self-hosted LLMs mean GPUs, which means the hosted
   free tier stops being free. The generous free tier is the marketing
   engine; breaking its cost model breaks the distribution strategy.
3. **Determinism.** LLM verdicts drifted between model versions and made
   regressions hard to debug. Rule-based detection is reproducible.
4. **Most of what the LLM did is now covered by rules.** The Deduce NER
   pass + the Meertens/CBS name lists + the function-title classifier
   (`backend/app/services/role_engine.py`) + the gemeente whitelist
   (`backend/app/services/whitelist_engine.py`) + the structure engine
   (`backend/app/services/structure_engine.py`) together handle the
   common cases the LLM used to catch.

See `docs/reference/woo-redactietool-analyse.md` and
`docs/todo/done/35-deactivate-llm.md` for the original analysis.

## Before you revive it

Read this list and answer each question in writing before you start
coding. "We want the LLM back" is not enough.

- What specific failure mode in the rule-based pipeline are you fixing?
  Cite real examples from `backend/tests/fixtures/` or pilot feedback.
  If the rules can plausibly be extended to cover the gap, extend the
  rules instead.
- How will operators opt in? The default must stay LLM-free. A
  self-hosting gemeente with no GPU must not accidentally depend on it.
- Who runs the inference? For hosted Gratis, is it still free? For Team
  / Enterprise, is the SLA realistic?
- Does the dev loop still work without Ollama running? Tests must pass
  offline; startup must not block on model load.
- How will you guarantee the text never hits a third-party API?
  Integration test that patches DNS / blocks outbound calls.

## Suggested shape if you do revive it

Keep it small and isolated. The old layer lived in `backend/app/llm/`
and had four files (`provider.py`, `ollama.py`, `prompts.py`,
`__init__.py`). That shape was fine — copy it if you like — but the
hooks into the pipeline matter more than the file layout.

1. **Settings** in `backend/app/config.py`: add `llm_verification_enabled:
   bool = False`, `ollama_base_url`, `ollama_model`. Default off. Never
   read from environment silently; the operator must set the flag
   explicitly.
2. **Provider interface** (abstract class with `classify_role` and
   `health_check`). Keep it narrow — one method per pipeline question.
3. **Ollama implementation** using `httpx` (already a dependency) and
   the Ollama tool-calling API. Budget a hard timeout (~5s per request).
   Retry once, then fall back to `pending` with the Deduce reasoning.
4. **Pipeline hook** in `backend/app/services/llm_engine.py`
   (`run_pipeline`): after the rule-based passes, before the fallback
   `_persoon_pending`, if `settings.llm_verification_enabled` is true,
   bucket the remaining Tier 2 `persoon` hits, call the provider with
   a ~200-character context window, and map the verdict onto
   `PipelineDetection`. Use a lazy import so the default path never
   touches the provider module.
5. **Tests**: offline-only, fake provider, verify the four branches
   (drop `not_a_person`, mark `public_official` as rejected, keep
   citizens/civil-servants pending with the model's reasoning, fall
   back to Deduce on any exception). Do *not* ship a test that starts
   a real Ollama process.
6. **Health endpoint**: `/api/health` may optionally report LLM
   reachability when the flag is on. It must still return 200 when the
   provider is down — the LLM is advisory, never required.
7. **Docs**: update `CLAUDE.md`, `backend/app/services/llm_engine.py`
   module docstring, and this file.

## Prompts

Historical prompts — role classification and content analysis — are
not kept in the tree. If you need them, pull commit `677f276` (the
"deactivate LLM + backlog renumber" commit) or `92c3b2e` (the tier-2
rule-based detection stack commit) from `git log`, look at
`backend/app/llm/prompts.py`, and port what you need. They are Dutch
templates tuned for Gemma-style tool calling; treat them as a
starting point, not gospel.

## Do NOT

- Do not pull in `anthropic`, `openai`, `google-genai`, `mistralai`, or
  any other hosted SDK.
- Do not ship model weights in the repo or in a Docker image.
- Do not make the LLM path the default. Ever.
- Do not log document text (client-first architecture — see
  `docs/todo/00-client-first-architecture.md`).
- Do not reintroduce `llm_tier3_enabled`. Tier 3 is still reserved for
  future rule-based content signals, not for an LLM content-analysis
  pass.
