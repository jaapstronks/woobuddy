# Name list sources

This directory holds the raw name lists consumed by
`backend/app/services/name_engine.py`. The detector normalizes them at
startup (lowercase, strip diacritics) into in-memory `frozenset`s used
to score Deduce `persoon` hits: a known first name or surname boosts
confidence, absence of both drops the detection.

## Files

### `Top_eerste_voornamen_NL_2017.csv`

Nederlandse Voornamenbank (NVB) — **Meertens Instituut KNAW**.

- Source: <https://www.meertens.knaw.nl/nvb>
- License: open access with attribution.
- Attribution requirement (cited verbatim by Meertens):
  > *"Meld bij presentatie elders dat de gegevens afkomstig zijn uit de
  > Nederlandse Voornamenbank van het Meertens Instituut KNAW (met
  > link www.meertens.knaw.nl/nvb)."*
- This attribution is surfaced in the Tier 2 review card whenever a
  detection was boosted by this list. See `Tier2Card.svelte`.
- The repo copy is a **seed subset** of common Dutch first names
  pending a direct download of the official CSV. Replacing the file
  with the full Meertens `Top_eerste_voornamen_NL_2017.csv` requires
  no code change — the loader reads the first column of each line
  (comments starting with `#` and blank lines are ignored).

### `cbs_achternamen.csv`

CBS achternamenbestand — **Centraal Bureau voor de Statistiek**.

- Source: CBS public data on Dutch surnames.
- License: public, unrestricted.
- The repo copy is a **seed subset** of common Dutch surnames. Replace
  with a larger CBS extract (top 5k–10k) in the same one-surname-per-line
  format to improve coverage. The loader is format-agnostic: it takes
  the first column, splitting on `;`, `,`, or tab.
- Leading tussenvoegsels (`van`, `de`, `der`, `ten`, `ter`, …) are
  handled separately in code. Do **not** include them in this file.

## Refreshing the lists

1. Download the latest CSV from the respective source.
2. Replace the file in place — keep the filename.
3. Restart the backend. The loader runs once at startup (see
   `main.lifespan`) and caches the normalized frozenset on
   `app.state.name_lists`. No build step.

## Format

Both files accept the same format:

- One name per line.
- First column is the name (split on `;`, `,`, or tab if present).
- Lines starting with `#` are comments.
- Blank lines are ignored.
- Case and diacritics do not matter — the loader normalizes both.

This means the raw Meertens CSV (`naam;geslacht;aantal`) and the CBS
file can drop in unmodified.
