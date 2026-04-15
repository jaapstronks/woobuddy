# 48 — Non-Dutch surname coverage for Tier 2 persoon detection

- **Priority:** P2
- **Size:** M (1–3 days)
- **Source:** Bug surfaced during 2026-04 inspraak-document test fixture
- **Depends on:** Nothing (additive to the existing Tier 2 rule stack)
- **Blocks:** Nothing

## Why

Tier 2 person detection leans heavily on the CBS achternamenlijst (`backend/app/data/cbs_achternamen_*.txt`) to confirm that a capitalized token is actually a Dutch surname. That works well for "Hendriks", "de Groot", "de Vries", "Bakker" — but it silently misses common non-Dutch surnames that are equally privacy-sensitive in a Woo context.

The regression that made this visible: an inspraak reactie paragraph mentioned **"de familie El Khatib (huisnummer 22)"** on the same line as "W. de Groot". The reviewer expected El Khatib to be redacted as persoon — it was not, because "Khatib" is not in the CBS achternamenlijst and the Dutch tussenvoegsel "El" is not in the `TUSSENVOEGSELS` set. Woo documents routinely name residents, ambtenaren, and inspraak-deelnemers with surnames of Arabic, Turkish, Moroccan, Surinamese, Polish, and other non-Dutch origins. Missing them is a real privacy leak, not just an accuracy inconvenience.

Adding every conceivable surname to a static list is intractable and not how the existing CBS list works anyway. The fix is a **second rule path**: detect a plausible name *without* requiring the surname to be in any wordlist, by leaning on surrounding structure (titles, tussenvoegsels, capitalization patterns) and on lightweight non-Dutch surname wordlists where we can get them.

## Scope

### 1. Broaden the tussenvoegsel set

Extend `TUSSENVOEGSELS` in the surname validator to include common non-Dutch particles:

- **Arabic/Maghrebi:** `el`, `al`, `abu`, `abd`, `ben`, `bin`, `ibn`
- **Turkish:** (typically none — handled in §3)
- **Portuguese/Brazilian/Italian:** `da`, `do`, `dos`, `das`, `di`, `del`, `della`
- **Spanish:** `de la`, `de los`, `de las` (already partially covered via `de`)
- **German:** `von`, `zu`, `vom` (already covered)

These are intentionally title-cased to match mid-sentence usage ("de familie **El** Khatib"). The existing Dutch tussenvoegsels stay untouched.

### 2. Title + capitalized-token rule

When a salutation/title immediately precedes one or more capitalized tokens, treat the sequence as a person name *regardless of whether the final token is in CBS*. Titles to anchor on (match the list used by todo #13's publiek-functionaris filter):

- `dhr.`, `mevr.`, `mw.`, `mr.`, `drs.`, `prof.`, `dr.`
- `de heer`, `mevrouw`, `meneer`
- `familie` / `de familie` (as seen in the El Khatib case)

The rule:

1. Match one of the titles above at word boundary.
2. Walk forward over optional single-letter initials (`W.`, `K.`) and known tussenvoegsels (Dutch + §1 extensions).
3. Consume one or more capitalized tokens (`[A-Z][a-zA-ZÀ-ÿ'\-]+`).
4. Emit a `persoon` detection spanning the final capitalized token(s), *not* the whole phrase — the same span the sidebar card and PDF overlay render after bbox-text-resolver slicing (#this-task).

This runs alongside CBS matching and produces lower confidence than a CBS-list hit (`confidence=0.75` vs `0.90`), because it has more false-positive potential (e.g. "de heer Voorzitter" in formal prose). The existing publiek-functionaris filter still suppresses hits that match `functietitels_publiek.txt`.

### 3. Optional: non-Dutch surname wordlists

Add optional seed wordlists (small, ~1–5k entries each) from public sources:

- `backend/app/data/achternamen_arabisch.txt`
- `backend/app/data/achternamen_turks.txt`
- `backend/app/data/achternamen_pools.txt`

These are *supplements* to the CBS list, not replacements. A token that matches any of them is treated exactly like a CBS hit.

Sources to consider: CBS already publishes frequency tables of surnames in NL regardless of origin — the issue is that the current WOO Buddy list is the top-N subset. Widening the slice to cover long-tail names (top-50k rather than top-10k, say) may already solve most of the non-Dutch coverage problem without needing separate files. Investigate first; separate files are the fallback.

### 4. Fixtures + tests

- Add a fixture PDF mirroring the inspraak paragraph: "de familie El Khatib (huisnummer 22)", "dhr. Bekir Yılmaz", "mevr. Agnieszka Kowalski", plus a Dutch name for baseline parity.
- Unit tests on `ner_engine.py` asserting each expected hit is produced and spans the correct characters.
- Regression test against the existing publiek-functionaris list so we don't redact "de heer Voorzitter" or "de burgemeester Rutte" as persoon.

## Out of scope

- First-name detection (Meertens voornamen) is already covered by the existing Tier 2 rule; this todo does not touch it.
- Full Unicode normalization for surname matching (`İ` → `I`, `ł` → `l`, etc.) can be a separate pass if false-negatives persist.
- Any LLM-based fallback. The dormant Ollama layer stays dormant (see `docs/reference/woo-redactietool-analyse.md` and the pivot note in `done/35-deactivate-llm.md`).

## Acceptance criteria

- A fixture PDF containing "de familie El Khatib", "dhr. Bekir Yılmaz", and "mevr. Agnieszka Kowalski" produces three `persoon` Tier 2 detections.
- "de heer W. de Groot" continues to be detected (CBS path) and its bbox covers only "W. de Groot".
- "de burgemeester Rutte" and "wethouder Van Delft" are NOT detected as persoon (publiek-functionaris filter still wins).
- The title+capitalized-token rule has its own confidence tier (`0.75`) and reasoning string (`"Naam herkend via titel + hoofdlettersequentie (niet in CBS-lijst)."`).
- `backend/app/services/ner_engine.py` unit tests cover each above case.
