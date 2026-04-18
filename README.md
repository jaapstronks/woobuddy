# WOO Buddy

**Jouw slimme assistent voor het lakken van Woo-documenten.**

WOO Buddy is een open-source, self-hostable webapplicatie die Nederlandse overheidsmedewerkers helpt bij het afhandelen van Woo-verzoeken (Wet open overheid). De tool detecteert privacygevoelige informatie in PDF-documenten en begeleidt een menselijke beoordelaar door het lakproces.

- **MIT-gelicenseerd**, inclusief self-host pad (`docker compose up` tegen één Postgres)
- **Geen taalmodel** in de codebase — detectie is 100% regex + Nederlandse NER + woordenlijsten + structuurheuristieken
- **Client-first**: PDF's verlaten nooit de browser van de gebruiker; de server slaat geen documentinhoud op
- **Gehoste versie**: <https://woobuddy.nl>

---

## Hoe het werkt

WOO Buddy gebruikt een **drietrapsraket** voor detectie. De waarde zit in een snelle, betrouwbare review-workflow, niet in een slimmer model.

| Tier | Wat | Detectie | Standaardgedrag |
|------|-----|----------|-----------------|
| **1** | Harde identifiers (BSN, IBAN, telefoon, e-mail, postcode, kenteken) | Regex + validatie (elfproef, Luhn) | Automatisch gelakt |
| **2** | Contextuele persoonsgegevens (namen, adressen, functies) | Deduce NER + voornamen-/achternamenlijsten + structuurherkenning + regel-gebaseerde publiek-functionaris filter | Gesuggereerd |
| **3** | Gereserveerd | — | — |

Elke tier krijgt een eigen UX — van automatische lakking (Tier 1) tot bulksweeps en per-kaart bevestiging (Tier 2). Waarom geen taalmodel: zie [`docs/reference/woo-redactietool-analyse.md`](docs/reference/woo-redactietool-analyse.md).

### Client-first architectuur

PDF's verlaten nooit de browser van de gebruiker. De server slaat geen documentinhoud op: tekstextractie gebeurt client-side via pdf.js, de rule-based analyse is vluchtig, en alleen beslissingen (bbox-coördinaten, entiteitstype, tier, artikel) worden in de database bewaard. Zie [`docs/todo/done/00-client-first-architecture.md`](docs/todo/done/00-client-first-architecture.md) voor de volledige specificatie.

**Uw documenten verlaten nooit uw infrastructuur en er komt geen taalmodel aan te pas.** Dat is de hele privacy-propositie, in één zin — geen verwerkersovereenkomst voor een modelhoster, geen GPU-beheer, geen uitleg over waar data naartoe gaat.

## Techstack

- **Frontend**: SvelteKit (Svelte 5 runes), Tailwind CSS v4, Shoelace, pdf.js
- **Backend**: FastAPI (Python 3.12), PyMuPDF, [Deduce](https://github.com/vmenger/deduce) (Nederlandse NER), SQLAlchemy v2
- **Infrastructuur**: PostgreSQL 16 (alleen metadata), Docker Compose

Voor de volledige licentie-overzicht van dependencies: zie [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md).

---

## Zelf draaien (self-host)

De snelste weg naar een draaiende instantie. Werkt op Mac, Linux en Windows zolang je Docker hebt.

### Vereisten

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Mac/Windows) of Docker Engine + compose plugin (Linux)
- Git
- ~2 GB vrije schijfruimte voor de images

### Starten

```bash
git clone https://github.com/jaapstronks/woobuddy.git
cd woobuddy
cp .env.example .env
docker compose up
```

De eerste build duurt een paar minuten. Klaar wanneer je `frontend-1 | Listening on http://0.0.0.0:3000` ziet.

Open vervolgens:

- **App**: <http://localhost:3000>
- **API-docs**: <http://localhost:8100/docs>

Upload een PDF op `/try` — je komt automatisch in het reviewscherm.

### Stoppen, updaten, opruimen

```bash
# Stoppen (of Ctrl+C in de terminal waar docker draait)
docker compose down

# Updaten naar de laatste commit
git pull
docker compose up --build

# Database volledig weggooien (let op: verwijdert alle reviews)
docker compose down -v
```

### In productie zetten

Er is een afzonderlijke `docker-compose.prod.yml` met Caddy als reverse proxy (HTTPS via Let's Encrypt) en een deploy-script in [`deploy/`](deploy/) dat een fresh Hetzner Ubuntu 24.04 VPS provisioneert. Lees [`deploy/install.sh`](deploy/install.sh) voor de precieze stappen — het is bewust klein en transparant.

---

## Ontwikkelen

### Zonder Docker (snellere iteratie)

Frontend en backend kun je bare-metal draaien. Je hebt alleen nog een draaiende Postgres nodig (`docker compose up postgres` is het makkelijkst).

#### Frontend

```bash
cd frontend
npm install
npm run dev
```

Draait op <http://localhost:5173>.

#### Backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Draait op <http://localhost:8000>.

> **Let op de poorten**: bare-metal uvicorn draait op `8000`, Docker Compose op `8100`. Zorg dat `PUBLIC_API_URL` in `frontend/.env` overeenkomt met je setup. Beide poorten staan toegestaan in de frontend-CSP.

### Commando's

```bash
# Frontend
cd frontend
npm run check         # TypeScript + Svelte typecheck
npm test              # Vitest

# Backend
cd backend && source .venv/bin/activate
ruff check app/       # Lint
ruff format app/      # Format
mypy app/             # Typecheck
pytest                # Tests
```

### Projectstructuur

```
woobuddy/
├── docker-compose.yml         # Dev stack: frontend, api, postgres
├── docker-compose.prod.yml    # Prod stack: + Caddy reverse proxy
├── deploy/                    # VPS provisioning & deploy scripts
├── frontend/                  # SvelteKit applicatie
│   └── src/
│       ├── lib/components/    # Svelte-componenten (landing, review, shared, ui)
│       ├── lib/stores/        # Svelte 5 runes-state
│       ├── lib/api/           # Getypte API-client
│       └── routes/            # SvelteKit-pagina's (/, /try, /review/[docId])
├── backend/                   # FastAPI applicatie
│   └── app/
│       ├── api/               # Route handlers
│       ├── services/          # Regex + Deduce + structuurherkenning + regels
│       ├── models/            # SQLAlchemy-modellen + Pydantic-schemas
│       └── db/                # Database sessie + migraties
└── docs/
    ├── reference/             # Architectuur, artikelen, revival-notes
    └── todo/                  # Backlog (open + done)
```

---

## Bijdragen

Issues, PRs en ideeën zijn welkom. Een paar vuistregels:

- **Client-first is heilig.** Als een feature lijkt te vereisen dat PDF's op de server worden opgeslagen, is het ontwerp fout. Zie [`docs/todo/done/00-client-first-architecture.md`](docs/todo/done/00-client-first-architecture.md).
- **Geen taalmodel terugbrengen** zonder expliciete productbeslissing. De LLM-laag is in april 2026 volledig verwijderd om de "uw PDF verlaat nooit uw browser"-belofte en het kostenmodel overeind te houden. Als je een lokale LLM-stap overweegt: begin bij [`docs/reference/llm-revival.md`](docs/reference/llm-revival.md).
- **UI in het Nederlands**, code en commits in het Engels.
- **Schrijf `WOO Buddy`** (WOO in kapitalen, Buddy met hoofdletter) in alle gebruikersgerichte tekst.

De roadmap staat in [`docs/todo/README.md`](docs/todo/README.md) — genummerde markdown-bestanden per feature, gegroepeerd in fases A t/m G.

## Licentie

MIT. Zie [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md) voor de licenties van de afhankelijkheden (met name PyMuPDF — AGPL-3.0 — en Deduce — LGPL-3.0).
