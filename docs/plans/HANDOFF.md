# Review en merge: PR #100 — leadformulier op woobuddy.nl repareren (#72)

**Model: Opus.** Modelkeuze: uitvoerrepo, geen signalen. De PR is uitvoerwerk met een
gemeten oorzaak en een toetsbaar acceptatiecriterium; de enige beslissing (afzenderdomein,
notificatie-adres) is al genomen. Escaleer naar Fable alleen als de review een
ontwerpvraag opgooit die de brief niet beantwoordt.

## Stand bij vertrek

2026-09-02, avond. **PR #100 wacht op Jaaps review en merge:**
https://github.com/jaapstronks/woobuddy/pull/100 — `feat/brevo-to-listmonk`, gerebased op
`main`, 13 bestanden. Frontend-CI groen; backend-CI stond nog te draaien bij vertrek.

Wat de PR doet: Listmonk + Scaleway TEM landen, de mailconfig via expliciete
`environment:`-regels in `docker-compose.prod.yml` naar de api-container krijgen,
`deploy.sh` die sleutels laten schrijven, een CR/LF-filter op `name`/`organization` vóór
Subject en Reply-To (vier nieuwe tests), en twee deploy-gates plus een startup-error zodat
een lege mailsleutel niet meer stilletjes kan shippen.

**Al gedaan buiten de repo:** Scaleway IAM-applicatie `woobuddy-leads`
(`982fc6f1-fe35-4222-93f1-4d99da9cdcef`), policy `woobuddy-leads-tem` met
`TransactionalEmailFullAccess` gescoped op alleen het Bolster-project, API-key
`SCW8VR5ZHG62XET92G4M`. Rechtstreeks tegen de TEM-API getest: HTTP 200, mail verstuurd
naar jaap@jaapstronks.nl. De secret staat als letterlijke waarde in de project-root `.env`
(gitignored), samen met project-id, afzender en de Listmonk-lijst-UUID.

Jaaps beslissingen deze sessie: notificatie-adres `jaap@jaapstronks.nl` (niet meer
jaapstronks@gmail.com — ook vastgelegd in `~/.claude/CLAUDE.md`), afzender voorlopig
`noreply@mail.dreamkit.eu`. #66 en #67 zijn bewust gesnoozed.

## Opdracht

1. `git pull`. Check `gh pr checks 100`; beide suites moeten groen zijn. Let op: de
   backend-suite kent één bekende faal op machines mét Ghostscript
   (`test_empty_redactions_returns_unmodified`, zie #67) — die telt niet mee.
2. Review PR #100 tegen `briefs/72-lead-form-broken-in-production.md`. Kijk specifiek naar
   het CR/LF-filter (`_clean(header_safe=True)` in `leads.py`) en naar de twee gates in
   `deploy/install.sh` — die zijn de hele bestaansreden van de brief.
3. Merge (squash) als het klopt. Branch wordt automatisch verwijderd.
4. **Deploy en verifieer.** `op run --env-file=.env -- ./deploy/deploy.sh` vanuit de
   repo-root. Daarna één echte inzending via het formulier op woobuddy.nl: verwacht een
   200 en een notificatiemail op jaap@jaapstronks.nl. Vink dan de drie
   acceptatiecriteria in de brief af.
5. Toets de gate één keer echt: maak `SCALEWAY_SECRET_KEY` in de project-root `.env`
   tijdelijk leeg en bevestig dat `deploy.sh` weigert te starten. Zet 'm daarna terug.
6. Sluit #72 af: brief naar `docs/plans/done/`, regel in `done/register.md`, item uit
   TODO.md naar _Recently done_, claimbord leegmaken. Draai daarna
   `merge-housekeeping`.
7. **Losse eindjes voor Jaap** (niet blokkerend voor de merge):
   - `op` is uitgelogd (`account is not signed in`), dus de Scaleway-secret staat als
     platte waarde in de project-root `.env` in plaats van in 1Password. Na `op signin`:
     item aanmaken in vault Bolster en de regel vervangen door een `op://`-referentie.
     `deploy/README.md` beschrijft de vorm.
   - `~/.claude/CLAUDE.md` wordt niet gesynct naar dev-server-1 (allowlist-`.gitignore`
     dekt alleen `skills/`, `commands/`, `bin/`). Het nieuwe mailadres-blok staat dus
     alleen op de Mac.
8. **Overschrijf dit bestand** met de handoff voor het volgende werk (model per
   `werkwijze` § Modelkeuze per sessie, met een `Modelkeuze:`-regel eronder) en sluit af
   met de sluitregel.

## Doorgeefblok

- **#68** (landingspagina zonder Shoelace, Nederlandse leadform-fouten): eerstvolgende
  uitvoeritem. #72 raakte `client.ts` alleen in een docstring, dus #68 kan er direct op
  bouwen.
- **#66** (P0) zodra Jaap het motivatieveld beslist heeft; **#67** zodra PDF/A beslist is.
  Beide bewust gesnoozed op 2026-09-02.
- **#71** deel "Now" (CI-stappen + CONTRIBUTING gelijktrekken) en **#63** zijn klein en
  direct delegeerbaar.
- Dependabot: `pdfjs-dist`-high (#92); #97/#98 checken.
- Losse eind: `noreply@woobuddy.nl` als TEM-domein inrichten vraagt SPF/DKIM/MX bij
  TransIP. Recept staat in `deploy/README.md`; verdient een eigen nummer als het gebeurt.

## Terugkeer-check

- [ ] Jaap: motivatieveld houden of schrappen? (#66) — gesnoozed 2026-09-02
- [ ] Jaap: PDF/A-2b wel of niet? (#67) — gesnoozed 2026-09-02
- [ ] Jaap: Notion-database "Woobuddy Todos" handmatig verwijderen (404 via de koppeling).
- [ ] Jaap: `op signin`, daarna de Scaleway-secret naar 1Password (vault Bolster).

## Extra van Jaap

_(leeg)_
