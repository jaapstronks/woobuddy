---
version: 0.0.0
date: 2026-01-01
summary: Eén zin die zegt wat er anders is aan het werk van de lezer.
latest: false
---

Een openingsalinea in gewone taal: wat is er veranderd, en waarom merkt een
beoordelaar dat. Geen opsomming van commits, geen versienummers in de tekst.

### Een kop per lezersvoordeel

Wat de gebruiker nu kan of niet meer hoeft, in twee of drie zinnen. Noem het
gedrag, niet de implementatie. Als iets stiller is geworden of juist strenger,
zeg dan wat dat betekent voor het aantal kaarten dat iemand langsloopt.

### Nog een voordeel

Ordenen op wat de lezer merkt, niet op wanneer het gebouwd is of onder welk
itemnummer.

---

**Schrijfregels voor deze map.**

- Eén bestand per versie: `<versie>.md`, bijvoorbeeld `0.3.0.md`. De bestandsnaam
  is het anker op `/changelog` en moet gelijk zijn aan `version`.
- Nederlands, en geschreven voor de ambtenaar die zit te lakken, niet voor een
  ontwikkelaar. De Engelse `CHANGELOG.md` in de repo doet het commit-verhaal al.
- Geen em-streepjes. Gebruik een gewoon streepje met spaties, of een punt-komma.
- `chore`, `refactor`, `docs` en `test` zijn geen release-note-materiaal. Als er
  in een versie niets zit dat een lezer merkt, hoort er ook geen note bij.
- `latest: true` staat op precies één note. Verhuis hem in dezelfde commit waarin
  je de nieuwe note toevoegt.
- `date` is de dag waarop de release-PR gemerged wordt. Staat die datum nog niet
  vast, zet dan de verwachte dag en corrigeer hem in dezelfde PR-ronde.
- De note voor een versie staat op `main` vóórdat de release-PR voor die versie
  gemerged wordt. Zie `docs/reference/versioning.md` → Release ritual.

Verwijder dit blok in een echte note; het staat hier alleen in het sjabloon.
