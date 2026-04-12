# WOO Buddy

**Jouw slimme assistent voor het lakken van Woo-documenten.**

WOO Buddy is an open-source, self-hostable web application that helps Dutch government employees process Woo (Wet open overheid) requests. It detects privacy-sensitive information in PDF documents and guides a human reviewer through the redaction process.

## How it works

WOO Buddy uses a **three-tier detection model** ("drietrapsraket"):

| Tier | What | Detection | Default state |
|------|------|-----------|---------------|
| **1** | Hard identifiers (BSN, IBAN, phone, email) | Regex + validation | Auto-redacted |
| **2** | Contextual personal data (names, addresses) | NER + role classification | Suggested |
| **3** | Content-level judgments (policy opinions, business data) | LLM analysis | Annotated |

Each tier gets a different UX pattern — from auto-redaction (Tier 1) to full decision support (Tier 3).

## Tech stack

- **Frontend**: SvelteKit (Svelte 5), Tailwind CSS v4, Shoelace, pdf.js
- **Backend**: FastAPI, PyMuPDF, Deduce (Dutch NER), SQLAlchemy v2
- **LLM**: Gemma 4 via Ollama (local, no data leaves the machine) — Anthropic API as fallback
- **Infrastructure**: PostgreSQL 16, MinIO (S3-compatible PDF storage), Docker Compose

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- [Ollama](https://ollama.com/) with `gemma4:26b` pulled (for LLM features)
- Node.js 22+ (for local frontend development)
- Python 3.12+ (for local backend development)

## Quick start

```bash
# 1. Clone the repository
git clone https://github.com/jaapstronks/woobuddy.git
cd woobuddy

# 2. Copy environment variables
cp .env.example .env

# 3. Pull the LLM model (first time only, ~18GB)
ollama pull gemma4:26b

# 4. Start all services
docker compose up
```

The application will be available at:
- Frontend: http://localhost:3000
- API: http://localhost:8000
- API docs: http://localhost:8000/docs
- MinIO console: http://localhost:9001

## Local development

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

## Project structure

```
woobuddy/
├── docker-compose.yml       # All services: frontend, api, postgres, minio
├── frontend/                # SvelteKit application
│   ├── src/
│   │   ├── lib/components/  # Svelte components (landing, review, dossier, etc.)
│   │   ├── lib/stores/      # Svelte 5 runes-based state
│   │   ├── lib/api/         # Typed API client
│   │   └── routes/          # SvelteKit pages
│   └── ...
├── backend/                 # FastAPI application
│   ├── app/
│   │   ├── api/             # Route handlers
│   │   ├── services/        # Business logic (PDF, NER, LLM engines)
│   │   ├── llm/             # LLM provider abstraction
│   │   ├── models/          # SQLAlchemy models + Pydantic schemas
│   │   └── db/              # Database session + migrations
│   └── tests/
└── docs/                    # Architecture and legal documentation
```

## License

MIT. See [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) for dependency licenses.
