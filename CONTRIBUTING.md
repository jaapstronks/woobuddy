# Bijdragen aan WOO Buddy

Welkom! WOO Buddy is een kleine, opinionated codebase met een helder doel: Nederlandse overheidsmedewerkers sneller en veiliger laten lakken. We accepteren graag bijdragen, maar de lat ligt hoog op twee punten — client-first architectuur en reviewbaar werk — omdat maintainertijd hier het schaarse goed is.

_English version below._

---

## Voordat je begint

1. **Lees [`README.md`](README.md) en [`CLAUDE.md`](CLAUDE.md).** Samen beschrijven ze de architectuur en de hardere ontwerpregels. Een PR die tegen die regels ingaat, halen we niet door — ongeacht hoe netjes de code is.
2. **Check de backlog.** Open issues en [`docs/todo/README.md`](docs/todo/README.md) laten zien waar we mee bezig zijn. Werk aan iets dat al gepland staat heeft een veel grotere kans om binnen te komen dan een verrassing.
3. **Open eerst een issue voor niet-triviale wijzigingen.** Een tien-regels bugfix mag direct als PR. Iets wat de UX, de API of de architectuur raakt: open eerst een discussie of een issue zodat we op hoofdlijnen aligneren voor je uren investeert.

## Kernregels

Deze staan niet ter discussie per PR — alleen per expliciet product-besluit.

- **Client-first architectuur.** PDF's verlaten nooit de browser van de gebruiker. De server slaat geen documentinhoud op. Als je feature dit lijkt te breken, is het ontwerp fout. Zie [`docs/todo/done/00-client-first-architecture.md`](docs/todo/done/00-client-first-architecture.md).
- **Geen taalmodel.** WOO Buddy draait 100% rule-based (regex + Deduce + woordenlijsten + structuurheuristieken). Voeg geen LLM-afhankelijkheid toe. Als je denkt er één nodig te hebben: lees eerst [`docs/reference/llm-revival.md`](docs/reference/llm-revival.md) en open een issue.
- **UI in het Nederlands**, code, commits en documentatie in het Engels.
- **Schrijf `WOO Buddy`** (WOO in kapitalen, Buddy met hoofdletter) in gebruikersgerichte tekst.

## Ontwikkelen

Zie [`README.md`](README.md) voor de install-stappen. Korte versie:

```bash
git clone https://github.com/jaapstronks/woobuddy.git
cd woobuddy && cp .env.example .env
docker compose up
```

Voor iteratieve ontwikkeling kun je frontend en backend bare-metal draaien (zie README).

### Checks die moeten slagen

Voor je een PR opent:

```bash
# Frontend
cd frontend && npm run check && npm test

# Backend
cd backend && source .venv/bin/activate
ruff check app/ && ruff format --check app/ && mypy app/ && pytest
```

CI draait dezelfde checks op elke PR. Falende CI = geen review.

## PR-richtlijnen

- **Scope klein houden.** Eén PR = één verandering. Refactors en feature-werk niet mixen.
- **Schrijf een testplan.** Wat heb je handmatig getest, met welke input, en wat was de verwachte uitkomst? Screenshots voor UI-werk, API-output of logs voor backend-werk.
- **Geen nieuwe dependencies** zonder reden in de PR-beschrijving. We houden de stack bewust klein.
- **Geen stilzwijgende gedragsveranderingen.** Als bestaand gedrag wijzigt, zet het expliciet in de PR-beschrijving en werk de tests bij.
- **Commits** bij voorkeur Conventional Commits-achtig (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`). Geen harde eis, wel prettig voor changelogs.

## AI-assistentie bij bijdragen

We zijn niet tegen AI-tools (sterker nog: delen van deze codebase zijn mede met behulp van Claude Code geschreven). Maar in 2026 is het genereren van een PR sneller dan hem reviewen, en dat betekent dat de verantwoordelijkheid voor kwaliteit bij jou ligt, niet bij de maintainers.

Gebruik je een AI-assistent voor het grootste deel van een PR? Dan geldt:

1. **Disclosure.** Vermeld in de PR-beschrijving welke tool je gebruikt hebt en waarvoor (bv. "Claude Code — implementatie en tests", "Copilot — autocomplete"). Minor autocomplete hoef je niet te noemen; AI als primaire auteur wel.
2. **Jij bent verantwoordelijk.** Je dient de PR in vanuit een persoonlijk account (geen botaccounts), en je staat achter elke regel. "De AI zei dit" is geen argument in review.
3. **Handmatig getest.** Bewijs dat het werkt: screenshots, testoutput, curl-calls. "Alle tests slagen" is geen bewijs dat je feature werkt — alleen dat je geen bestaand gedrag hebt gesloopt.
4. **Lees je eigen diff.** Als je de diff niet regel-voor-regel kunt verdedigen in review, is de PR nog niet klaar om in te dienen.

### Wat we direct sluiten

- Bulk-PRs die typo's, whitespace of formatting "fixen" zonder aantoonbare toegevoegde waarde.
- PRs die de README, docs of comments "verbeteren" met gegenereerde prose die feitelijk niet klopt.
- PRs die dependencies bumpen zonder changelog-review of testrun.
- Vertalingen door AI-tools voor de Nederlandse UI-teksten — Nederlandse copy schrijven we handmatig.
- PRs die hetzelfde probleem oplossen als een openstaande PR, zonder naar die andere PR te linken.

Dit is niet bedoeld om AI-gebruikers te ontmoedigen; het is bedoeld om review-tijd te beschermen. Een goed gelande AI-assisted PR met disclosure is net zo welkom als een handgeschreven PR.

## Beveiligingsmeldingen

Open **geen** publiek issue voor beveiligingsproblemen. Zie [`SECURITY.md`](SECURITY.md) voor het melden via GitHub Private Vulnerability Reporting of e-mail.

## Gedragscode

Dit project volgt de [Contributor Covenant 2.1](CODE_OF_CONDUCT.md). Meldingen: `jaapstronks@gmail.com`.

## Licentie

Door een PR in te dienen ga je akkoord met publicatie onder de [MIT-licentie](LICENSE) van dit project.

---

## English

WOO Buddy is a small, opinionated codebase. Contributions welcome, but the bar is high on two axes — client-first architecture and reviewable work — because maintainer time is the scarce resource here.

**Before you start:** read [`README.md`](README.md) and [`CLAUDE.md`](CLAUDE.md). For non-trivial changes, open an issue first.

**Core rules** (not up for debate per PR):

- Client-first: PDFs never leave the browser; the server stores no document content.
- No LLM in the default path. See [`docs/reference/llm-revival.md`](docs/reference/llm-revival.md) before considering one.
- UI text in Dutch; code, commits, docs in English.

**PR guidelines:** one change per PR, include a manual test plan (screenshots for UI, output for backend), no new dependencies without justification, all CI checks must pass.

**AI-assisted contributions** (the 2026 reality):

- Disclose when AI is the primary author of a PR.
- You're accountable for every line — submit from a personal account, defend the diff in review.
- Include evidence that you manually tested the change. "Tests pass" is not evidence your feature works, only that you didn't break existing behavior.
- We close AI bulk-typo-fix / doc-"improvement" / dependency-bump PRs on sight.

**Security reports:** see [`SECURITY.md`](SECURITY.md). Do not file public issues.

**Code of conduct:** [Contributor Covenant 2.1](CODE_OF_CONDUCT.md). Reports: `jaapstronks@gmail.com`.

By opening a PR you agree your contribution is published under the project's [MIT license](LICENSE).
