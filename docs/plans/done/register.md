# Register — gesloten werk

Eén regel per afgesloten item: wat, wanneer, waar het bewijs staat. Nieuwe regels
onderaan per maand. De write-ups zelf blijven als bestand in deze map staan.

## 2026-04

- **#00 Client-First Architecture (PDFs Never Stored on Server)** — de fundamentele
  keuze: de PDF verlaat de browser niet, de server verwerkt tekst efemeer en bewaart
  alleen metadata (geen `entity_text`, geen MinIO). Landde vóór het PR-workflow
  (`8079ab8`). Zie [`00-client-first-architecture.md`](00-client-first-architecture.md). (2026-04-13)
- **#01 Testing Foundation** — pytest-suite op de backend (76 tests: Tier 1-regex,
  Deduce, pipeline, propagatie) plus frontend-tests, tegen de client-first datastroom.
  Commit `8079ab8`. Zie [`01-testing-foundation.md`](01-testing-foundation.md). (2026-04-13)
- **#02 Error Handling** — nette afhandeling van corrupte, scanned en
  wachtwoordbeveiligde PDF's, netwerkuitval, te grote bestanden en volle IndexedDB,
  met Nederlandse foutteksten. Commit `8079ab8`. Zie
  [`02-error-handling.md`](02-error-handling.md). (2026-04-13)
- **#03 Security Hardening** — magic-byte-check client-side, `backend/app/security.py`
  met slowapi-rate limits, security headers en proxy-secret, en `Detection.entity_text`
  definitief uit het datamodel. Commit `8079ab8`. Zie
  [`03-security-hardening.md`](03-security-hardening.md). (2026-04-13)
- **#04 Structured Logging** — structlog met JSON-output, request-scoped
  `request_id`/`user_id`/`organization_id` via contextvars, uvicorn-access uitgezet
  zodat er nooit documenttekst in de logs belandt. Frontend-errortracking bewust
  uitgesteld. Commit `8079ab8`. Zie [`04-structured-logging.md`](04-structured-logging.md). (2026-04-13)
- **#05 Review/Edit Mode Toggle** — dezelfde viewer met twee modi (M-toets of
  toolbar), de poort naar alle handmatige bewerkfuncties. Commit `c1d4df7`.
  Zie [`05-mode-toggle.md`](05-mode-toggle.md). (2026-04-13)
- **#06 Manual Text Selection Redaction** — slepen over de pdf.js-tekstlaag snapt naar
  woordgrenzen, levert per regel bboxen op en gaat via een formulier (Woo-grond,
  entiteitstype, motivering) naar `POST /api/detections`; de server ziet de tekst nooit.
  Commit `c1d4df7`. Zie [`06-manual-text-redaction.md`](06-manual-text-redaction.md). (2026-04-13)
- **#07 Area Selection Redaction** — vlakselectie als vluchtweg voor handtekeningen,
  stempels, foto's en scanfragmenten die de tekstlaag niet kan bereiken; hergebruikt de
  actiebalk en het formulier van #06. Commit `c1d4df7`. Zie
  [`07-area-selection.md`](07-area-selection.md). (2026-04-13)
- **#08 Undo / Redo** — `Ctrl+Z` / `Ctrl+Shift+Z` / `Ctrl+Y` over de detectiestore,
  met de bestaande guard voor focus in invoervelden inclusief Shoelace-elementen.
  Commit `c1d4df7`. Zie [`08-undo-redo.md`](08-undo-redo.md). (2026-04-13)
- **#09 Search-and-Redact** — volledig client-side zoeken over de al geëxtraheerde
  tekst (`search-redact.ts`); alleen de bulk-create raakt de server. Commit `c1d4df7`.
  Zie [`09-search-and-redact.md`](09-search-and-redact.md). (2026-04-13)
- **#10 Page Completeness Review** — pagina-status (unreviewed / in_progress /
  complete / flagged) met indicatoren en auto-status, zodat aantoonbaar is dat elke
  pagina is bekeken. PR #4. Zie [`10-page-completeness.md`](10-page-completeness.md). (2026-04-15)
- **#11 Boundary Adjustment** — resize-handles op bestaande detecties in Edit Mode,
  zodat een te ruime of te krappe bbox wordt bijgesteld in plaats van afgewezen en
  opnieuw getekend. PR #4. Zie [`11-boundary-adjustment.md`](11-boundary-adjustment.md). (2026-04-15)
- **#12 Name lists: Meertens voornamen + CBS achternamen** — open naamlijsten als
  regelgebaseerde vervanger van de LLM-verificatiepas, waarmee Deduce-`persoon`-hits
  worden bevestigd of weggefilterd. PR #4. Zie
  [`12-name-lists-meertens-cbs.md`](12-name-lists-meertens-cbs.md). (2026-04-15)
- **#13 Functietitel + publiek-functionaris rule engine** — namen voorafgegaan door een
  Nederlandse functietitel krijgen automatisch `rejected` (publiek functionaris) of een
  voorgevulde `subject_role = 'ambtenaar'`; lijst in
  `backend/app/data/functietitels_publiek.txt`. PR #4. Zie
  [`13-functietitel-publiek-functionaris.md`](13-functietitel-publiek-functionaris.md). (2026-04-15)
- **#14 Structuurherkenning (e-mailheaders, handtekeningblokken, aanhef)** — regelgebaseerde
  `StructureSpan`-detectie van de plekken waar privacygevoelige tekst structureel staat,
  goed voor hogere precisie, betere redenen op de kaart en een aangrijpingspunt voor #20.
  PR #4. Zie [`14-structuurherkenning.md`](14-structuurherkenning.md). (2026-04-15)
- **#15 Tier 2 Suggestion Card UX** — de suggestiekaart kreeg zichtbare gelakt-status
  met per-kaart undo, een Woo-grond-picker en drie rolchips (burger / ambtenaar /
  publiek functionaris), voorgevuld door de regelengine. PR #4. Zie
  [`15-tier2-suggestion-ux.md`](15-tier2-suggestion-ux.md). (2026-04-15)
- **#16 Tier 1 gaps: KvK, BTW, geboortedatum** — drie ontbrekende regexpatronen met
  contextuele verankering toegevoegd aan `detect_tier1`, waarmee de regel-only stack
  compleet is. PR #4. Zie [`16-tier1-gaps.md`](16-tier1-gaps.md). (2026-04-15)
- **#17 Publieke functionarissen referentielijst (per-document)** — de reviewer zaait
  eenmalig de namen van bijvoorbeeld het college van B&W; elke latere vermelding wordt
  automatisch afgewezen, ook zonder titel ervoor. Client-first in IndexedDB. PR #4.
  Zie [`17-publieke-functionarissen-referentielijst.md`](17-publieke-functionarissen-referentielijst.md). (2026-04-15)
- **#18 Split and Merge Detections** — een detectie splitsen als er twee gronden onder
  liggen, of aangrenzende detecties samenvoegen tot één lakking. PR #4. Zie
  [`18-split-merge.md`](18-split-merge.md). (2026-04-15)
- **#19 Redaction Log & Audit Trail** — route `/review/[docId]/log` met statistiektegels,
  samengestelde filters, sorteerbare tabel, uitklapbare detailrijen en een batchtoolbar;
  zonder entiteitstekst, dus client-first. PR #4. Zie
  [`19-redaction-log.md`](19-redaction-log.md). (2026-04-15)
- **#20 Bulk sweep flows (header block, signature block, same-name)** — drie
  eenkliksveegacties bovenop de structuurspans; vergde wel `start_char`/`end_char` op het
  `Detection`-model om containment te kunnen bepalen. PR #4. Zie
  [`20-bulk-sweep-flows.md`](20-bulk-sweep-flows.md). (2026-04-15)
- **#21 Per-document custom wordlist ("eigen zoektermen")** — eigen termen die de
  reviewer per document opgeeft, blijven bewaard en worden bij elke analyse opnieuw
  toegepast met `source="custom_wordlist"`. PR #4. Zie
  [`21-per-document-custom-wordlist.md`](21-per-document-custom-wordlist.md). (2026-04-15)
- **#22 Loading States & Skeleton Screens** — laadtoestanden voor de upload-analyse-flow,
  de eerste render van het reviewscherm en alle operaties boven 500 ms, zodat er geen
  lege schermen of layout shifts meer zijn. PR #4. Zie
  [`22-loading-states.md`](22-loading-states.md). (2026-04-15)
- **#23 Landing Page Animations** — CSS-bewegingsprimitieven (`.fade-in-up` e.d.) op de
  landingspagina; de reviewinterface bleef bewust onbewogen, snelheid gaat daar boven
  fraaiheid. PR #4. Zie [`23-animations.md`](23-animations.md). (2026-04-15)
- **#24 Mobile Responsive Polish** — landingspagina en instapflow gecontroleerd en
  bijgewerkt voor mobiel; het reviewscherm blijft desktop-only per ontwerp. PR #4.
  Zie [`24-mobile-responsive.md`](24-mobile-responsive.md). (2026-04-15)
- **#35 Deactivate LLM layer** — de LLM uit de live pipeline gehaald ten gunste van
  regex, wordlists en structuurheuristiek; scheelt GPU, modelhosting, verwerkersovereenkomst
  en DPIA. De code bleef toen nog als geparkeerd revival-pad in de boom staan
  (inmiddels verwijderd). PR #4. Zie [`35-deactivate-llm.md`](35-deactivate-llm.md). (2026-04-15)
- **#44 Sample Documents on Landing Page (Zero-Upload Trial)** — "Probeer met een
  voorbeelddocument" haalt de uploadangst weg: de hele lus (detectiekaarten, lakken,
  exporteren) op een fictief Woo-verzoek zonder eigen bestand. PR #4. Zie
  [`44-sample-documents-landing.md`](44-sample-documents-landing.md). (2026-04-15)
- **#45 Lead Capture Email Form** — leadformulier dat contacten rechtstreeks naar Brevo
  lijst 4 duwt, zonder Postgres-persistentie of CSV-export; DNS voor `hoi@woobuddy.nl`
  via TransIP geregeld. (Vervanging door Listmonk + Scaleway TEM staat op de nog
  ongemergde branch `feat/brevo-to-listmonk`, zie `decisions.md`.) PR #4.
  Zie [`45-lead-capture.md`](45-lead-capture.md). (2026-04-15)
- **#48 Non-Dutch surname coverage for Tier 2 persoon detection** — tweede regelpad dat
  namen als "de familie El Khatib" herkent zonder dat de achternaam in de CBS-lijst
  staat, op basis van tussenvoegsels, titels en kapitalisatiepatronen. Let op: het
  nummer 48 is dubbel vergeven (zie ook de toegankelijke PDF-export hieronder). PR #4.
  Zie [`48-non-dutch-surnames.md`](48-non-dutch-surnames.md). (2026-04-15)
- **#40 Legal Pages & SEO** — routegroep `(legal)` met vier SSR-pagina's (privacy,
  voorwaarden, DPA, cookies), per pagina meta- en OG-tags, herbouwde footer en
  uitgebreide `sitemap.xml`. PR #6. Zie [`40-legal-seo.md`](40-legal-seo.md). (2026-04-16)
- **#49 In-Browser OCR for Scanned / Image-Only PDFs** — OCR in de browser met een
  parallelle tekstmap in IndexedDB in plaats van een onzichtbare-tekst-PDF, zodat
  `bbox-text-resolver`, `search-redact` en de detectiestore ongewijzigd blijven werken.
  PR #6. Zie [`49-in-browser-ocr.md`](49-in-browser-ocr.md). (2026-04-16)
- **#51 Microsoft 365 / Google Drive file picker (client-side)** — provider-agnostische
  `pickFromProvider()` met Graph File Picker v8 en de Google Picker API, SDK's lazy
  geladen van de CDN van de provider; het bestand raakt onze server nooit. PR #9.
  Zie [`51-microsoft-google-file-picker.md`](51-microsoft-google-file-picker.md). (2026-04-18)
- **#41 Analytics (Plausible, self-hosted)** — Plausible Community Edition op een eigen
  site-identiteit (`analytics.woobuddy.nl`), funnel-events standaard uitgeschakeld.
  PR #24; later nog opgeschoond in PR #40 en PR #53. Zie
  [`41-analytics.md`](41-analytics.md). (2026-04-19)
- **#48 Accessible PDF Export (Language Tag, XMP, PDF/A-2b)** — taalmarkering, XMP-metadata,
  toegankelijke lakmarkeringen en PDF/A-2b-conformiteit op de geëxporteerde PDF; PDF/UA-1
  en de machineleesbare inventaris bleven bewust uitgesteld. Let op: het nummer 48 is
  dubbel vergeven (zie ook de niet-Nederlandse achternamen hierboven). PR #36. Zie
  [`48-accessible-pdf-export.md`](48-accessible-pdf-export.md). (2026-04-26)
- **#43 Open Source Release: cut v0.1.0 + publish images** — tag `v0.1.0` op `19613ea`,
  multi-arch GHCR-images voor api en frontend, en een release-workflow die op elke
  `v*`-tag bouwt en publiceert. PR #43. Zie
  [`43-open-source-release.md`](43-open-source-release.md). (2026-04-26)
- **#52 DiWoo / TOOI publication metadata export** — exportknop die client-side een zip
  bouwt met de gelakte PDF, DiWoo-XML v0.9.8, een GPP-Woo `metadata.json`,
  `redaction-log.csv` zonder entiteitstekst en een Nederlandse README. PR #37. Zie
  [`52-diwoo-publication-metadata-export.md`](52-diwoo-publication-metadata-export.md). (2026-04-26)
- **#64 Onderbouwingsrapport export (audit log als Woo-besluit-bijlage)** — leesbaar
  Nederlands PDF-rapport dat per lakking de grond en motivering geeft, client-side
  gerenderd met een lazy geladen pdf-lib. PR #55. Zie
  [`64-onderbouwingsrapport-export.md`](64-onderbouwingsrapport-export.md). (2026-04-28)
- **#65 Tagged PDF + bookmarks voor het onderbouwingsrapport (PDF/UA-1)** — structuurboom,
  ParentTree en outlines toegevoegd in pdf-lib in plaats van via de PyMuPDF-route uit de
  oorspronkelijke spec, die geen structuur kan synthetiseren. PR #56. Zie
  [`65-onderbouwingsrapport-tagged-pdf.md`](65-onderbouwingsrapport-tagged-pdf.md). (2026-04-28)
- **#50 Anonymous analyze: no server persistence** — de anonieme flow schrijft niets meer
  naar Postgres: analyse zonder `document_id`, detecties inline terug, export met de lijst
  in de request body, en een IndexedDB-sessiecache zodat Cmd+R het werk niet wist.
  Geleverd in PR #47 en PR #48; de bijbehorende boekhoudcommit `4e322ed` bleef ongemergd
  op `chore/close-50` staan tot de migratie hem op 2026-09-02 alsnog meenam. Zie
  [`50-anonymous-no-persist.md`](50-anonymous-no-persist.md). (2026-04-28)

## 2026-09

- **Backlog-migratie `docs/todo/` → `docs/plans/` + tighten-scan-briefs #66–#71** — de
  universele werkwijze ingericht (TODO/briefs/done/HANDOFF/_reconcile), 39 write-ups en
  34 open items verhuisd, #50 administratief gesloten, #62 afgevoerd. Zes nieuwe briefs uit
  de scan van 2026-09-02, bij review op alle `file:regel`-claims nagelezen. PR #99. (2026-09-02)

## Historisch

- **WOO_BUDDY_TODO.md** — persoonlijke setup-lijst uit het Ollama-tijdperk, alleen als
  geschiedenis bewaard; verwijst naar `backend/app/llm/`, dat niet meer bestaat. Zie
  [`WOO_BUDDY_TODO.md`](WOO_BUDDY_TODO.md). (2026-04-15)

## Afgevoerd zonder uitvoering

- **#62 Notion-cross-references** — vervallen op 2026-09-02, nooit gebouwd: de repo
  gebruikt Notion niet meer voor todo's, `docs/plans/` is de enige backlog.
