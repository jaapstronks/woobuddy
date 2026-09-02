# Drift-log — housekeeping-ledger

Signalen die tussen twee diepe audits door opvallen. `merge-housekeeping` schrijft hier
één regel per signaal; `reorg-audit` leest ze, handelt ze af en reset de teller.

**Open signalen:** 0
**Laatste diepe audit:** 2026-09-02 (tighten-scan, zie briefs #66–#71)
**Merges sinds die audit:** 1
**Nudges sinds laatste audit:** 0

> Drempel voor een `reorg-audit`: ≥ 5 open signalen, óf één `[CONFLICT]`, óf ≥ 10 merges
> sinds de laatste audit.

## Open

_(leeg)_

### Log per merge

- **2026-09-02 · PR #99** (docs: backlog naar `docs/plans/`, briefs #66–#71) — `clean`.
  Ondiepe scan: claimbord leeg, geen `[DONE?]`/`[CONFLICT]`, geen brief zonder
  TODO-item (34 briefs ↔ 34 open items), TODO 476 regels (< 1.200). Review-correcties
  (77 links, roadmap-link, briefs 66/68/69/71, Listmonk-formulering) zijn in de PR
  zelf geland. PR #49 (`chore/close-50`) gesloten als vervangen. Ongepland werk
  ontdekt tijdens de review (leadformulier op productie geeft 500) heeft direct een
  adres gekregen: #72, bovenaan blok A.
