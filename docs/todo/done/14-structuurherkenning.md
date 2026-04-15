# 14 — Structuurherkenning (e-mailheaders, handtekeningblokken, aanhef)

- **Priority:** P1
- **Size:** M (1–3 days)
- **Source:** `docs/reference/woo-redactietool-analyse.md` §"Wat moet er zwartgelakt worden?" (E-mailheaders en handtekeningblokken) + pivot decision in `done/35-deactivate-llm.md`
- **Depends on:** #35 (LLM dormant), #12 (name lists — the structure engine cross-references them)
- **Blocks:** #20 (bulk sweeps key off the spans this todo emits)

## Why

The analyse.md identifies structure-based detection as the single biggest unused signal: in a Woo-besluit or email thread, the most privacy-sensitive text is almost always in a structurally predictable place — the `Van: / Aan: / CC:` block, the signature after "Met vriendelijke groet", the aanhef "Geachte heer/mevrouw X". Detecting those regions gives us three things at once:

1. **Higher precision on name detection.** A Deduce `persoon` hit inside a signature block or email header is almost never a false positive — the structure itself is the evidence.
2. **A target for bulk sweeps (#20).** "Lak alles in dit e-mailheaderblok in één klik" is only possible once we know where the block starts and ends.
3. **A reason string the reviewer trusts.** "Naam in handtekeningblok" is a much more convincing label on a Tier 2 card than a generic "Deduce-detectie".

This is pure rule-based pattern matching. No ML, no wordlists beyond what #12 already ships.

## Scope

### Structure engine module

- [ ] New `backend/app/services/structure_engine.py` with one public function:
  - `detect_structures(extraction: ExtractionResult) -> list[StructureSpan]` — scans the full text and returns a list of labeled spans.
  - `StructureSpan` dataclass: `kind: Literal["email_header", "signature_block", "salutation"]`, `start_char: int`, `end_char: int`, `confidence: float`, `evidence: str` (the trigger text — "Met vriendelijke groet", "Van:", etc.).

### E-mail header detection

- [ ] Trigger: a line starting with one of `Van:`, `Aan:`, `CC:`, `Bcc:`, `Onderwerp:`, `Verzonden:`, `Datum:` (case-insensitive, whitespace tolerant).
- [ ] Extent: the block ends at the first blank line, the first non-header-looking line, or after 15 consecutive header-shaped lines (whichever comes first). A "header-shaped line" is `^\s*[A-Z][A-Za-z]+:` followed by non-empty content.
- [ ] Multiple headers in one document (forwarded / replied email threads) produce multiple spans.
- [ ] Edge case: PDF extraction often breaks headers across text items. The existing frontend smart-joining in `PdfViewer.svelte` helps, but the detector must tolerate whitespace anomalies in the middle of a header value.

### Signature block detection

- [ ] Trigger: one of `Met vriendelijke groet`, `Met vriendelijke groeten`, `Hoogachtend`, `Met hartelijke groet`, `Vriendelijke groet`, `Groet,` (line-anchored, case-insensitive).
- [ ] Extent: the next 2–6 non-blank lines after the trigger, stopping at a second blank line, a salutation keyword, or a Tier 1 match that looks like a disclaimer URL.
- [ ] Should cope with `Met vriendelijke groet,\n\nName\nFunction\nOrganization\nPhone\nEmail` — all of those are part of the signature.

### Aanhef (salutation) detection

- [ ] Trigger: `^Geachte\s+(heer|mevrouw|heer/mevrouw|heer en mevrouw)\b`, also `^Beste\s+\w+\b`, `^L\.S\.\b`, `^Geachte\s+[A-Z]` (fallback when no title).
- [ ] Extent: the trigger line only. The target is the single name/title on that line.
- [ ] Salutations are a strong "this is a private citizen being addressed" signal — the detector boosts Tier 2 `persoon` confidence *inside* the salutation line and hints to the rule engine (#13) that the subject is probably *not* a public official.

### Integration with the pipeline

- [ ] `llm_engine.run_pipeline` calls `detect_structures` once on the extracted text, attaches the resulting spans to `PipelineResult` (new field: `structure_spans: list[StructureSpan]`).
- [ ] For each Tier 2 `persoon` detection, check if its span falls inside any structure span:
  - Inside an `email_header` or `signature_block`: boost confidence by +0.15 (cap 0.95), auto-accept (`review_status="auto_accepted"`) **unless** #13's rule engine has already marked it `publiek_functionaris` → keep that decision.
  - Inside a `salutation`: boost by +0.10, keep `pending` but set `subject_role="burger"` as a pre-fill (citizens being addressed are private persons).
  - Reason string includes "Naam in handtekeningblok" / "Naam in e-mailheader" / "Naam in aanhef".
- [ ] The structure spans are also returned to the frontend (new field on `AnalyzeResponse`) so #20 can render "sweep this block" affordances.

### Tests

- [ ] `tests/test_structure_engine.py`:
  - Fixture: a typical Dutch Woo email with `Van:`, `Aan:`, signature, and body text. Expect three `email_header` spans (thread) and two `signature_block` spans; verify offsets.
  - Fixture: a letter starting with "Geachte heer Jansen," → one `salutation` span.
  - Fixture: plain body text with no structure → empty list.
- [ ] `tests/test_llm_engine.py` regression: a fixture where a Tier 2 name inside a signature block is auto-accepted (not pending).

## Acceptance criteria

- `detect_structures` emits spans for the three structure types on realistic fixtures.
- Names inside a detected signature block auto-accept with reasoning "Naam in handtekeningblok".
- Names inside a detected email header auto-accept with reasoning "Naam in e-mailheader".
- The frontend receives the structure spans and can render them (wiring in #20 and #15).
- The noise regression from #35 is further narrowed: fewer `pending` cards on the standard fixture set after #12, #13, and #14 all land.

## Not in scope

- Disclaimer block detection (the boilerplate "Deze e-mail is vertrouwelijk..." footer). Worth a follow-up todo if it turns out to be frequent.
- Header-parsing for structured email fields like date formats — the detector only cares about the block extent, not semantic extraction of the fields.
- Pdf.js column or layout detection beyond what text extraction already provides.

## Files likely to change

- `backend/app/services/structure_engine.py` (new)
- `backend/app/services/llm_engine.py` (integration + new field on PipelineResult)
- `backend/app/api/schemas.py` (new field on AnalyzeResponse)
- `backend/app/api/analyze.py` (return the structure spans)
- `backend/tests/test_structure_engine.py` (new)
- `backend/tests/test_llm_engine.py` (regression)
- `frontend/src/lib/types/index.ts` (type for structure spans)
- `frontend/src/lib/api/client.ts` (consumed by #20)
