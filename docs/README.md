# Documentatie

WOO Buddy: client-first lakassistent voor Woo-documenten (SvelteKit + FastAPI, geen LLM).

| Doc | Doel |
|---|---|
| [`../README.md`](../README.md) | Wat het is, lokaal draaien, poorten |
| [`plans/TODO.md`](plans/TODO.md) | Wat er open staat, op prioriteit: het nu-document |
| [`plans/HANDOFF.md`](plans/HANDOFF.md) | De opdracht voor de eerstvolgende sessie (`/handoff`) |
| [`self-hosting/`](self-hosting/) | Zelf hosten: file-picker-configuratie |
| [`../deploy/README.md`](../deploy/README.md) | Productie-deploy (Hetzner + Caddy + Compose) |

```
docs/
├── README.md              # deze kaart
├── plans/                 # verandering: wat we gaan doen
│   ├── TODO.md            # claimbord + open werk + recently done
│   ├── HANDOFF.md         # wegwerp-opdracht voor de volgende sessie
│   ├── briefs/NN-slug.md  # uitwerking per open item (statusregel bovenaan)
│   ├── done/              # geshipte write-ups, register.md, decisions.md
│   └── _reconcile/        # drift-log.md (housekeeping-ledger)
├── reference/             # hoe het werkt: drietrapsraket, Woo-artikelen, analyses, bron-briefings
└── self-hosting/          # operator-documentatie voor zelf hosten
```

`reference/` beschrijft wat ís, `plans/` wat verandert. Werkwijze: skill `werkwijze` in `~/.claude`; repo-parameters in `CLAUDE.md` § Werkwijze.
