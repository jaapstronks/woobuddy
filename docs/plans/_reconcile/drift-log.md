# Drift-log — housekeeping-ledger

Signalen die tussen twee diepe audits door opvallen. `merge-housekeeping` schrijft hier
één regel per signaal; `reorg-audit` leest ze, handelt ze af en reset de teller.

**Open signalen:** 0
**Laatste diepe audit:** 2026-09-02 (tighten-scan, zie briefs #66–#71)
**Merges sinds die audit:** 0
**Nudges sinds laatste audit:** 0

> Drempel voor een `reorg-audit`: ≥ 5 open signalen, óf één `[CONFLICT]`, óf ≥ 10 merges
> sinds de laatste audit.

## Open

_(leeg)_

### Log per merge

_(nog geen gedelegeerde merges sinds workflow-init 2026-09-02)_
