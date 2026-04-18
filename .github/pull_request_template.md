<!--
Bedankt voor je bijdrage! Lees CONTRIBUTING.md voordat je dit invult.
PRs zonder testplan of (indien van toepassing) AI-disclosure worden teruggegeven.
-->

## Wat verandert er?

<!-- Korte, concrete beschrijving. Wat doet deze PR, en waarom? -->

## Gelinkte issue / backlog-item

<!-- Bv. "Closes #123" of "Refs docs/todo/XX-foo.md" -->

## Testplan

<!--
Hoe heb je dit HANDMATIG getest? CI-groen is geen bewijs dat je feature werkt,
alleen dat je geen bestaand gedrag hebt gesloopt. Plak screenshots voor UI-werk,
curl-output of logs voor backend-werk.
-->

- [ ] Frontend: `cd frontend && npm run check && npm test` — slaagt
- [ ] Backend: `cd backend && source .venv/bin/activate && ruff check app/ && mypy app/ && pytest` — slaagt
- [ ] Handmatig getest (beschrijf hieronder wat je deed):

## Architectuurchecks

- [ ] Deze PR respecteert de **client-first architectuur** (geen server-side opslag van documentinhoud, geen logs met tekstinhoud).
- [ ] Deze PR introduceert **geen LLM-afhankelijkheid** in het default pad.
- [ ] Gebruikersgerichte tekst is in het **Nederlands**; code/commits/docs in het **Engels**.
- [ ] Geen nieuwe dependencies toegevoegd — of wel, en hieronder verantwoord waarom.

## AI-assistentie (verplicht invullen)

Zie [CONTRIBUTING.md § AI-assistentie](../blob/main/CONTRIBUTING.md#ai-assistentie-bij-bijdragen).

- [ ] Deze PR is **handgeschreven**, met hooguit minor autocomplete van een IDE-assistent.
- [ ] Deze PR is **met AI-hulp** geschreven en ik ben verantwoordelijk voor elke regel:
  - Tool(s) gebruikt: <!-- bv. Claude Code, Cursor, Copilot -->
  - Waarvoor: <!-- bv. implementatie + tests / alleen boilerplate / refactor voorstel -->
  - Ik heb de diff regel-voor-regel gelezen en kan 'm in review verdedigen: **ja/nee**

## Screenshots / output

<!-- Optioneel maar vaak erg behulpzaam. -->
