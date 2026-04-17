# 59 — Zaaksysteem connectors (plugin architecture spike)

- **Priority:** P3 (sales-driven, far-future)
- **Size:** L (architecture) + M per connector
- **Source:** Competitor landscape 2026-04 — where Woo-verzoeken actually live in gemeenten
- **Depends on:** #32 (auth), #33 (organizations), #53 (dossier mode), #51 (file picker — shares auth patterns)
- **Blocks:** Nothing in the critical path; this is a growth lever

## Why

Woo-verzoeken don't originate in WOO Buddy — they arrive through a gemeente's **zaaksysteem**: Djuma, Decos JOIN, Corsa, Centric Suite for Zaakgericht Werken, OpenZaak, and a handful of smaller platforms. A reviewer today has to:

1. See the verzoek in the zaaksysteem
2. Download the relevant documents
3. Upload them to WOO Buddy
4. Review, redact, export
5. Re-upload the redacted files back into the zaaksysteem
6. Log the actions in the zaaksysteem for the audit chain

Steps 2, 3, 5, and 6 are friction that a zaaksysteem connector collapses into "WOO Buddy appears as a button inside the zaaksysteem." Every major competitor (INDICA, Novadoc, ilionx) has some form of this; it's the single biggest reason large-gemeente buyers go with an incumbent over us.

But connectors are a **growth lever, not a product**. Building them speculatively is how you end up with 5 half-finished integrations nobody uses. The shape of this todo is therefore:

1. A **plugin architecture spike** so that when the first pilot demands a connector we can build it in days, not weeks.
2. A **pilot-driven rollout**: first connector is whichever zaaksysteem the first paying Team pilot uses. Additional connectors come one-per-pilot.

## Scope — Phase 1 (the spike)

### Architecture

- [ ] **Plugin interface** in `$lib/integrations/` with two surfaces:
  - **Ingestion**: given a zaak-id and user auth, fetch the document list and let the reviewer pick which to ingest. Returns a list of `File` objects (client-side download where possible, server-proxy where required by the platform's auth model).
  - **Publication**: given a dossier's redacted output, upload back to the zaaksysteem with the right metadata + link to the original zaak.
- [ ] **Auth model per connector**: most zaaksystemen support OAuth2 (OpenZaak ZGW APIs) or API-key per org. Vendor per-connector auth code; don't try to build a universal auth abstraction.
- [ ] **Client-first where possible, server-proxy where required**: OpenZaak exposes a CORS-friendly ZGW API and can run entirely client-side. Legacy systems (Decos v4 SOAP) will require a server-side proxy — this is the one place we accept a server-side document touch, because the zaaksysteem's auth model doesn't let us do otherwise. **Treat the server-proxy path as an audited exception** (per the existing feedback memory on "no server touch on document bytes"), isolated to a dedicated `app/integrations/` module with explicit logging of "zaaksysteem X touched document Y at time Z" for the audit log.

### Pilot selection order

- [ ] **First connector: OpenZaak** (ZGW APIs) — open, CORS-friendly, client-first-compatible, well-documented. Use it as the reference implementation that proves the plugin architecture.
- [ ] **Second connector: whichever zaaksysteem the first paying pilot uses.** Do not pre-build Decos, Djuma, etc. based on market-share guesses — let a pilot force the priority.

### UX

- [ ] Settings panel per organization: "Zaaksysteem-koppelingen" with one card per installed connector, credentials input, test-connection button, enable/disable toggle
- [ ] Ingestion entry point: extend the `/try` (and dossier overview) upload area with "Haal uit zaaksysteem →" button that opens a picker UI specific to the connector
- [ ] Publication: dossier export screen gains a "Terugzetten naar zaaksysteem" option that uploads the redacted bundle to the origin zaak

### Tests

- [ ] Each connector ships with a local mock server in `tests/fixtures/zaaksysteem-mocks/` so we can integration-test without a real zaaksysteem

## Scope — Phase 2 (connector-per-pilot)

Repeat per pilot request:
1. Spec the connector from the pilot's documentation
2. Implement ingestion, then publication
3. Ship behind a per-org feature flag so the pilot can use it while others stay on manual upload
4. Promote to general availability after the pilot has used it in production for a full month

## Acceptance (for the spike)

- Plugin architecture documented in `docs/integrations/` with a working OpenZaak reference implementation
- OpenZaak connector can ingest documents from a zaak, review them in WOO Buddy, and publish the redacted output back
- Server-proxy exception is clearly demarcated in code and documented; no accidental creep into non-zaaksysteem code paths
- Connector code lives behind per-org feature flags — no unflagged connectors in production

## Not in scope

- M365/Teams integration (different platform, belongs to #51 + a future Teams-app todo)
- E-archief integration (ArchiveSpace, Preservica) — out of V1
- Generic "ZGW-compliant" dashboard for browsing all zaken — out of scope, we're a redaction tool, not a zaaksysteem
- Pre-building Decos/Djuma/Corsa connectors without a pilot commitment — explicitly rejected

## Open questions

- Does the server-proxy exception need its own legal review (DPA implications)? Yes — loop in counsel before the second connector is sold, since it changes the trust story for that specific customer.
- Pricing: bundled with Team tier, or an Enterprise-only add-on? Recommendation: OpenZaak is free (it's the open-source reference); vendor connectors are Enterprise add-ons because each one is vendor-negotiation work.

## Strategic note

This todo is the single biggest "talk to the customer, not to your codebase" item in the backlog. Don't start Phase 1 until we have credible signal from Phase D / E that a Team pilot will pay for it. Pre-building on spec is how this turns into months of wasted work.
