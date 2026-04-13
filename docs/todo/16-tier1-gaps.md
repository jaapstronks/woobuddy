# 16 — Tier 1 gaps: KvK, BTW, geboortedatum

- **Priority:** P2
- **Size:** S (< 1 day)
- **Source:** `docs/reference/woo-redactietool-analyse.md` §"Categorie 1: Herkenbare patronen"
- **Depends on:** #35 (LLM dormant — this is a completeness pass on the regex-only stack)
- **Blocks:** Nothing

## Why

The analyse.md lists KvK-nummers, BTW-nummers, and geboortedatums alongside BSN/IBAN/postcode/kenteken as patterns that can be caught with pure regex + validation. Today `ner_engine.detect_tier1` covers BSN, IBAN, email, telefoon, postcode, kenteken, URL, and creditcard. Adding the missing three is a small, self-contained change that improves Tier 1 coverage without adding any new architectural pieces.

## Scope

### KvK number

- [ ] Pattern: 8 consecutive digits, optionally preceded by `KvK`/`kamer van koophandel`/`KVK` within 20 characters. Standalone 8-digit sequences are ambiguous (could be many things), so require contextual anchoring to avoid false positives.
- [ ] Entity type: `kvk`. Woo-artikel: `5.1.2e` (KvK is a personal identifier when linked to a natural person; check with the juridisch analyse before committing the article).
- [ ] Confidence 0.90.

### BTW number

- [ ] Pattern: `NL` + 9 digits + `B` + 2 digits, with optional spaces. Examples: `NL123456789B01`, `NL 123456789 B 01`.
- [ ] Entity type: `btw`. Woo-artikel: same as KvK — subject to analysis.
- [ ] Confidence 0.95 (the format is strict enough).

### Geboortedatum

- [ ] Pattern: a date in one of the common Dutch formats (`dd-mm-jjjj`, `dd/mm/jjjj`, `d MMM jjjj`) immediately preceded (within 20 characters) by `geboortedatum`, `geboren op`, `geb.`, `geb:`, `DOB`, or `date of birth` (case-insensitive).
- [ ] Plain dates without the anchor remain Tier 2 (Deduce already catches some, with high false-positive rate). The anchor is what makes this Tier 1.
- [ ] Entity type: `geboortedatum`. Woo-artikel: `5.1.2e`.
- [ ] Confidence 0.95.

### Validation

- [ ] KvK: no checksum algorithm exists publicly, so length + context is the bar.
- [ ] BTW: the Dutch BTW format technically has a checksum (11-proef on the 9 digits), same as BSN. Apply the same `_validate_bsn` helper (renamed to `_validate_elfproef` if we want to reuse it cleanly, or inline the check).
- [ ] Geboortedatum: parse into a `datetime.date` and reject impossible dates (month > 12, day > 31 for the month) and dates more than 120 years in the past or any in the future.

### Tests

- [ ] `test_ner_engine.py` gains cases for each of the three new types:
  - KvK with and without context anchor (only with-anchor should match).
  - BTW with valid and invalid checksum.
  - Geboortedatum with each of the three date formats and each of the five anchor phrases.
  - False-positive fixtures: plain dates without anchor, 8-digit sequences in random body text.

## Acceptance criteria

- All three new types surface in `detect_tier1` output for the fixture documents.
- No regressions in existing Tier 1 tests.
- The new types render correctly in `Tier1Card.svelte` (their entity_type badges display; a fallback badge works even if we don't add a specific color).
- Checksums reject invalid BTW numbers with the same rigor as BSN.

## Not in scope

- Tier 2 (context-only) date detection. Kept out — false positives on plain dates are the reason the analyse.md lists geboortedatum as context-anchored.
- Buitenlandse BTW-nummers (DE, BE, FR variants). Dutch only for now.
- IBAN variants from non-NL countries. Already out of scope; #35 kept the existing NL-only IBAN regex.

## Files likely to change

- `backend/app/services/ner_engine.py`
- `backend/tests/test_ner_engine.py`
- `frontend/src/lib/types/index.ts` (new entity_type values in badge rendering if it's a closed union)
- `frontend/src/lib/components/review/Tier1Card.svelte` (verify new badges render)
