# Beslissingen — decision record

Eén regel per genomen beslissing: wat, wanneer, waarom, waar het uitgeschreven staat.
Alleen beslissingen die het gedrag van toekomstige sessies sturen.

## 2026

- **2026-04 — Client-first: PDF's verlaten de browser nooit, de server slaat geen documentinhoud op.**
  Fundament van alles; export is de enige (in-memory) uitzondering. Uitgeschreven in
  [`00-client-first-architecture.md`](00-client-first-architecture.md). Aangescherpt: ook
  vluchtige server-side conversie/OCR wordt afgewezen (OCR is in-browser, #49).
- **2026-04 — Geen LLM in de codebase.** Ollama/Gemma-laag verwijderd; detectie is regex +
  Deduce + woordenlijsten + structuurheuristiek. Een revival is alleen lokaal en opt-in:
  [`../../reference/llm-revival.md`](../../reference/llm-revival.md), rationale
  [`../../reference/woo-redactietool-analyse.md`](../../reference/woo-redactietool-analyse.md),
  uitvoering [`35-deactivate-llm.md`](35-deactivate-llm.md).
- **2026-04 — Open core met een royale gratis tier.** Self-host is een volwaardige tier (#43);
  de gehoste gratis tier heeft geen loginmuur, geen documentcap, geen watermerk. Billing
  gate't teamfeatures, nooit de reviewloop. Verworpen alternatieven (trial-cap, watermerk,
  preview-only) staan in [`backlog-README-2026-04.md`](backlog-README-2026-04.md) § Briefings
  Not Adopted.
- **2026-04 — Launch-volgorde: eerst publiek shippen en meten, dán pas auth/teams.**
  Geen auth vóór de Phase-D-poort ("bouw geen teamfeatures voordat een teamlead erom vraagt");
  draft-workflow alleen voor betalende pilots; Mollie pas na handmatige facturen. Tekst in
  [`backlog-README-2026-04.md`](backlog-README-2026-04.md) § GTM & launch sequencing.
- **2026-04 — Anonieme analyse persisteert niets** (#50): geen Document- of Detection-rijen
  voor `/api/analyze`; reviewstate leeft in IndexedDB. Zie [`50-anonymous-no-persist.md`](50-anonymous-no-persist.md).
- **2026-07-08 — Leadformulier van Brevo naar Listmonk + Scaleway TEM** (EU-infra van
  Dreamkit). Nog niet gemerged: branch `feat/brevo-to-listmonk`; landt via #72, want op
  productie heeft het formulier nooit mailconfig gehad (gemeten 2026-09-02).
- **2026-09-02 — Backlog van `docs/todo/` naar `docs/plans/` (universele werkwijze); Notion
  afgevoerd.** De Notion-database "Woobuddy Todos" wordt niet meer bijgehouden; #62
  (Notion-kruisverwijzingen) is zonder uitvoering afgevoerd. In-repo en getrackt ondanks
  de publieke repo: de backlog was al publiek. Briefs houden hun nummer als adres.

## Open beslissingen (wachten op Jaap)

- **Motivatietekst per detectie**: houden (dan echt opslaan en tonen in log/onderbouwing)
  of schrappen? Zie [`../briefs/66-redaction-correctness-bugs.md`](../briefs/66-redaction-correctness-bugs.md).
- **PDF/A-2b bij export**: wel (Ghostscript in Dockerfile + CI, `/Lang` ná de conversie) of
  niet (conversie en tempfile weg)? Zie [`../briefs/67-export-chain-accessibility-and-async.md`](../briefs/67-export-chain-accessibility-and-async.md).
- **Postgres in het default-pad**: nu dood gewicht; opties in
  [`../briefs/70-structure-consolidation.md`](../briefs/70-structure-consolidation.md) § E.
