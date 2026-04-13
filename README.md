# WOO Buddy

**Jouw slimme assistent voor het lakken van Woo-documenten.**

WOO Buddy is een open-source, self-hostable webapplicatie die Nederlandse overheidsmedewerkers helpt bij het afhandelen van Woo-verzoeken (Wet open overheid). De tool detecteert privacygevoelige informatie in PDF-documenten en begeleidt een menselijke beoordelaar door het lakproces.

## Hoe het werkt

WOO Buddy gebruikt een **drietrapsraket** voor detectie:

| Tier | Wat | Detectie | Standaardgedrag |
|------|-----|----------|-----------------|
| **1** | Harde identifiers (BSN, IBAN, telefoon, e-mail) | Regex + validatie | Automatisch gelakt |
| **2** | Contextuele persoonsgegevens (namen, adressen) | NER + rolclassificatie | Gesuggereerd |
| **3** | Inhoudelijke oordelen (beleidsopvattingen, bedrijfsgegevens) | LLM-analyse | Geannoteerd |

Elke tier krijgt een eigen UX — van automatische lakking (Tier 1) tot volledige beslissingsondersteuning (Tier 3).

### Client-first architectuur

PDF's verlaten nooit de browser van de gebruiker. De server slaat geen documentinhoud op: tekstextractie gebeurt client-side, analyse is vluchtig, en alleen beslissingen (bbox-coördinaten, entiteitstype, tier, artikel) worden in de database bewaard. Zie `docs/todo/00-client-first-architecture.md` voor de volledige specificatie.

## Techstack

- **Frontend**: SvelteKit (Svelte 5 runes), Tailwind CSS v4, Shoelace, pdf.js
- **Backend**: FastAPI, PyMuPDF, Deduce (Nederlandse NER), SQLAlchemy v2
- **LLM**: Gemma 4 via Ollama (lokaal, geen data verlaat de machine) — Anthropic API als alternatief
- **Infrastructuur**: PostgreSQL 16, Docker Compose

---

## Aan de slag op een Mac (met VS Code)

Deze handleiding gaat ervan uit dat je op een MacBook werkt, VS Code gebruikt en nog geen Docker hebt geïnstalleerd. Plan een rustig uurtje in — er zitten een paar downloads tussen, maar moeilijk is het niet. Als je ergens vastloopt: screenshot van de terminal + browser console en vraag het team om mee te kijken.

### 1. Installeer de basics

Open Terminal (⌘+spatie → "Terminal"). Installeer eerst [Homebrew](https://brew.sh) als je dat nog niet hebt:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Daarna in één keer Docker Desktop, Node en Git:

```bash
brew install --cask docker
brew install node git
```

Start **Docker Desktop** één keer vanuit je Programma's-map zodat het op de achtergrond draait (je ziet een walvis-icoontje in je menubalk). Zonder draaiende Docker werkt de rest niet.

### 2. Accepteer de GitHub-uitnodiging

Check je mail, klik op "View invitation" en accepteer. Daarna heb je toegang tot de repo.

### 3. Kloon het project via VS Code

1. Open VS Code.
2. ⌘+Shift+P → typ `Git: Clone` → Enter.
3. Plak: `https://github.com/jaapstronks/woobuddy.git`
4. Kies een map (bv. `~/Github`) en open het project als VS Code daarom vraagt.
5. Installeer eventueel de aanbevolen extensies die VS Code suggereert (Svelte, Python, Ruff).

### 4. Maak het `.env`-bestand aan

Open de ingebouwde terminal in VS Code (⌃+`) en draai:

```bash
cp .env.example .env
```

### 5. Kies je LLM-route

Tier 3 (de inhoudelijke content-analyse) heeft een taalmodel nodig. Je hebt twee opties:

**Optie A — Lokaal met Ollama (privacyvriendelijk, maar ±18 GB download):**

```bash
brew install ollama
ollama serve &
ollama pull gemma4:26b
```

**Optie B — Cloud via Anthropic (sneller van start, geen grote download):**

Open `.env` in VS Code en pas aan:

```
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

Voor een eerste rondrit is **Optie B** het snelst — dan draai je binnen tien minuten. Ollama kun je er later altijd nog bij zetten.

### 6. Start alles op

In de VS Code terminal:

```bash
docker compose up
```

De eerste keer duurt dit een paar minuten (Docker bouwt de frontend- en backend-images). Als je onderin `frontend-1  | Listening on http://0.0.0.0:3000` ziet, is het klaar.

Open in je browser: **http://localhost:3000**

Upload een PDF op `/try` en je komt vanzelf in het reviewscherm terecht.

### 7. Stoppen en opnieuw starten

- Stoppen: `Ctrl+C` in de terminal waar docker draait, of `docker compose down`
- Opnieuw starten: `docker compose up`
- Na code-wijzigingen van een collega: `git pull` en dan `docker compose up --build`

### Handig om te weten

- **Alles draait lokaal.** PDF's worden bewust nooit op de server opgeslagen — dat is een kernprincipe. Sluit je een tab, dan is je document weg.
- **De UI is in het Nederlands**, code en commits zijn in het Engels.
- **Frontend draait op** <http://localhost:3000>, **API op** <http://localhost:8100> (API-docs: <http://localhost:8100/docs>).

---

## Lokale development zonder Docker

Voor snellere iteratie kun je frontend en backend ook bare-metal draaien. Let op: je hebt dan nog steeds een draaiende Postgres nodig (`docker compose up postgres` is de makkelijkste manier).

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

> **Let op de poorten:** bare-metal uvicorn draait op `http://localhost:8000`, Docker Compose op `http://localhost:8100`. Zorg dat `PUBLIC_API_URL` in `frontend/.env` overeenkomt met je setup. Beide poorten staan toegestaan in de frontend-CSP.

### Commando's

- **Frontend typecheck**: `cd frontend && npm run check`
- **Backend lint**: `cd backend && source .venv/bin/activate && ruff check app/`
- **Backend format**: `cd backend && source .venv/bin/activate && ruff format app/`
- **Backend typecheck**: `cd backend && source .venv/bin/activate && mypy app/`
- **Backend tests**: `cd backend && source .venv/bin/activate && pytest`

## Projectstructuur

```
woobuddy/
├── docker-compose.yml       # Services: frontend, api, postgres
├── frontend/                # SvelteKit applicatie
│   ├── src/
│   │   ├── lib/components/  # Svelte-componenten (landing, review, shared, ui)
│   │   ├── lib/stores/      # Svelte 5 runes-state
│   │   ├── lib/api/         # Getypte API-client
│   │   └── routes/          # SvelteKit-pagina's
│   └── ...
├── backend/                 # FastAPI applicatie
│   ├── app/
│   │   ├── api/             # Route handlers
│   │   ├── services/        # PDF-, NER- en LLM-engines
│   │   ├── llm/             # LLM-provider abstractie
│   │   ├── models/          # SQLAlchemy-modellen + Pydantic-schemas
│   │   └── db/              # Database sessie + migraties
│   └── tests/
└── docs/                    # Architectuur, todo-backlog en juridische documentatie
```

## Licentie

MIT. Zie [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) voor de licenties van de afhankelijkheden.
