# Uitvoer: #72 Leadformulier op woobuddy.nl repareren (Listmonk-branch landen + Scaleway TEM via CLI)

**Model: Opus.** Modelkeuze: uitvoerrepo, brief is uitvoeringsklaar met een gemeten
oorzaak en een toetsbaar "klaar als"; geen signalen. De enige beslissing (notificatie-adres,
afzenderdomein) staat expliciet in de brief onder "Jaap beslist"; alles daarbuiten is
uitvoerwerk.

## Stand bij vertrek

2026-09-02, avond. PR #99 (backlog naar `docs/plans/`, briefs #66–#71) is gemerged;
`origin/main` staat op de squash-commit daarvan. Claimbord leeg. **Productie-bevinding
van vanavond:** `POST /api/leads` op woobuddy.nl geeft een 500 omdat de api-container
geen mailconfig krijgt (alle `BREVO_*` leeg, prod-compose geeft alleen `DATABASE_URL`
door). Jaap: verhuizen naar Scaleway TEM, inrichten mag via `scw`. Alles staat in
`briefs/72-lead-form-broken-in-production.md`. `feat/brevo-to-listmonk` (c1ee83d) staat
lokaal op de Mac, ongepusht, 20+ commits achter main. Twee oudere beslissingen wachten nog
op Jaap (motivatieveld #66, PDF/A #67).

## Opdracht

1. `git pull`, lees `briefs/72-lead-form-broken-in-production.md` integraal. Claim #72 op het
   claimbord in `TODO.md` (`#72 — @mbp — feat/brevo-to-listmonk — klaar als: …`).
2. `git checkout feat/brevo-to-listmonk && git rebase origin/main`. Los conflicten op (de
   branch raakt `leads.py`, `config.py`, `schemas.py`, `client.ts`, `.env.example`,
   `test_leads_api.py`). `pytest` groen.
3. Drie scanpunten op de branch: (a) `docker-compose.prod.yml` § `api` krijgt
   `env_file: .env`; `deploy/deploy.sh` schrijft de mailsleutels naast `DBASE_PASSWORD`;
   (b) CR/LF-filter op `name`/`organization` vóór ze in een mailheader gaan (test erbij);
   (c) Brevo-narratie uit `leads.py` en de `#45`-docstring.
4. Fail-loud: startup-warning bij lege `scaleway_secret_key` buiten dev, en een smoke-check
   in `deploy/install.sh` die faalt als de mailconfig ontbreekt.
5. Scaleway via CLI, profiel `bolster` (stappen in de brief): IAM-applicatie + policy +
   API-key → 1Password (vault Bolster). Afzender voorlopig `noreply@mail.dreamkit.eu`
   (al geverifieerd). Listmonk-lijst-UUID uit de Listmonk-admin.
6. Push, PR openen (`feat(leads): migrate lead form to Listmonk + Scaleway TEM and wire
   prod mail config`, template uit CLAUDE.md, < 400 regels waar mogelijk; de branch is al
   ~250 regels, dus splits de compose/deploy-wijziging af als het boven de 400 komt).
   `claude-notify-pr` afvuren. **Merge niet zelf.**
7. Na Jaaps merge (of met zijn akkoord in dezelfde sessie): `deploy/deploy.sh` met de
   nieuwe `.env`-sleutels, dan één echte testinzending → 200 en mail in
   `NOTIFICATION_EMAIL`. Acceptatiecriteria in de brief afvinken.
8. **Overschrijf dit bestand** met de review-en-merge-handoff voor jouw PR (model per
   `werkwijze` § Modelkeuze per sessie; default Opus, `Modelkeuze:`-regel eronder) en sluit
   af met de sluitregel.

## Doorgeefblok

- **#68** (landingspagina zonder Shoelace, Nederlandse leadform-fouten): delegeerbaar,
  volgende na #72. Let op: #72 raakt `client.ts`; #68 bouwt daar de `detail`-parsing op.
- **#66** (P0) zodra Jaap het motivatieveld beslist heeft; **#67** zodra PDF/A beslist is.
- **#71** deel "Now" (CI-stappen + CONTRIBUTING gelijktrekken) en **#63** zijn klein en
  direct delegeerbaar.
- Dependabot: `pdfjs-dist`-high (#92); #97/#98 checken.

## Terugkeer-check

- [ ] Jaap: `NOTIFICATION_EMAIL` voor leads, en afzender op `mail.dreamkit.eu` laten of
      `woobuddy.nl` als TEM-domein inrichten? (#72)
- [ ] Jaap: motivatieveld houden of schrappen? (#66)
- [ ] Jaap: PDF/A-2b wel of niet? (#67)
- [ ] Jaap: Notion-database "Woobuddy Todos" handmatig verwijderen (404 via de koppeling).

## Extra van Jaap

_(leeg)_
