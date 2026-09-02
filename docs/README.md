# Documentatie

WOO Buddy: client-first lakassistent voor Woo-documenten (SvelteKit + FastAPI, geen LLM).

| Doc | Doel |
|---|---|
| [`../README.md`](../README.md) | Wat het is, lokaal draaien, poorten |
| [`reference/client-first-architecture.md`](reference/client-first-architecture.md) | De architectuurregel waar al het andere aan moet voldoen |
| [`self-hosting/`](self-hosting/) | Zelf hosten: file-picker-configuratie |
| [`../deploy/README.md`](../deploy/README.md) | Productie-deploy (Hetzner + Caddy + Compose) |

```
docs/
├── README.md              # deze kaart
├── reference/             # hoe het werkt: client-first spec, drietrapsraket,
│                          #   Woo-artikelen, analyses, bron-briefings
└── self-hosting/          # operator-documentatie voor zelf hosten
```

`reference/` beschrijft wat ís. De worklist en de per-item briefs (`docs/plans/`)
zitten in een private sibling-repo en worden er als symlink in gehangen; ze zijn
bewust geen onderdeel van deze open-source repo. Wat er open staat is zichtbaar
in de [issues](https://github.com/jaapstronks/woobuddy/issues).
