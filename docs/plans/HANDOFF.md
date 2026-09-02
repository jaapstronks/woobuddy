# Review-en-merge: PR #99 (backlog naar docs/plans + tighten-scan-briefs #66–#71)

**Model: Fable.** Modelkeuze: standaard (review-en-merge draait op Fable). Inhoudelijk
extra reden: de PR bevat naast een mechanische verhuizing zes nieuwe briefs met
bevindingen die nog niemand tegen de code heeft nagelezen behalve de sessie die ze schreef.

## Stand bij vertrek

2026-09-02, avond. `origin/main` = `83fecbb`. Branch `docs/tighten-scan-2026-09`,
**[PR #99](https://github.com/jaapstronks/woobuddy/pull/99)**: docs-only, geen productiecode.
Claimbord leeg. `feat/brevo-to-listmonk` (c1ee83d, Listmonk-migratie) staat nog **lokaal**
op Jaaps Mac, 20 commits achter main, niet gepusht. Open Dependabot-PR's #97/#98 en een
**high**-alert op `pdfjs-dist` (< 6.2.108).

## Opdracht

1. `git pull`, `gh pr checkout 99`. Lees `docs/plans/TODO.md` en `done/register.md`
   integraal: dit is de eerste versie, geschreven door Opus-subagents op basis van de
   briefs. Toets steekproefsgewijs vijf "Klaar als"-regels tegen de acceptatiecriteria in
   de bijbehorende brief, en drie register-datums tegen `git log`.
2. Lees de zes nieuwe briefs (`briefs/66-*.md` t/m `71-*.md`) met de code ernaast. Elke
   bevinding draagt een `file:regel`; controleer er per brief minstens twee. Klopt een
   claim niet, corrigeer de brief in de PR (geen code aanraken).
3. Controleer dat er geen `docs/todo`-verwijzing meer over is
   (`git grep -n docs/todo`) en dat alle relatieve links in `docs/plans/` resolven.
4. CI groen (Frontend tests + Backend tests), dan **squash-mergen**; branch is auto-delete.
5. `merge-housekeeping`: teller in `_reconcile/drift-log.md` op 1, register-regel voor
   deze PR, TODO-omvang meten.
6. Vraag Jaap om de twee open beslissingen in `done/decisions.md` (motivatieveld,
   PDF/A): zonder antwoord kan #66 en #67 niet op Opus.
7. **Schrijf de volgende handoff** (dit bestand overschrijven): heeft Jaap beslist →
   uitvoer #66 (Opus); anders uitvoer #68 (Opus, delegeerbaar, geen beslissing nodig).
   Sluit af met de sluitregel.

## Doorgeefblok

- **#66** (P0) zodra het motivatieveld beslist is; **#67** zodra PDF/A beslist is.
- **#68** is direct delegeerbaar; **#71** deel "Now" ook (CI-stappen + CONTRIBUTING).
- `feat/brevo-to-listmonk`: vóór pushen de drie punten uit de scan meenemen
  (prod-compose zonder `env_file`, CR/LF-filter op `name`/`organization`, Brevo-comments).
- Dependabot: `pdfjs-dist`-high; check of #97/#98 mergebaar zijn (Dependabot-auto-merge
  pakt alleen minor/patch).

## Terugkeer-check

- [ ] Jaap: motivatieveld houden of schrappen? (#66)
- [ ] Jaap: PDF/A-2b wel of niet? (#67)
- [ ] Jaap: Notion-database "Woobuddy Todos" handmatig verwijderen; vanuit de
      Claude-Code-koppeling is die niet bereikbaar (404).

## Extra van Jaap

_(leeg)_
