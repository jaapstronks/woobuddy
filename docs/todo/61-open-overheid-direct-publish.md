# 61 — Direct publication to open.overheid.nl (GPP-publicatiebank)

- **Priority:** P3 (sales-driven — don't build before a pilot customer asks)
- **Size:** L (3–7 days, larger if we end up owning an OAuth flow)
- **Source:** Competitor landscape 2026-04 + transparency-framing conversation 2026-04
- **Depends on:** #52 (DiWoo/TOOI bundle must exist first)
- **Blocks:** Nothing

## Why

WOO Buddy's framing so far is internal-facing: "we help Woo-reviewers lak sneller." Closing the loop to [open.overheid.nl](https://open.overheid.nl) flips the framing outward: *we help burgers eerder en completer inzicht krijgen in overheidsinformatie, door het publicatietraject voor reviewers drempelloos te maken.* That's a stronger brand story than a redaction tool alone and a concrete answer to competitors (Novadoc, EntrD) that advertise "zoeken + lakken + publiceren" as one flow.

#52 already produces a DiWoo/TOOI-compliant bundle. This todo is the next step: **one-click publish** from the review screen into whatever publication endpoint the organization uses — typically a [GPP-publicatiebank](https://github.com/GPP-Woo/GPP-publicatiebank) instance, which is the open-source reference implementation feeding open.overheid.nl.

## Client-first tension (READ THIS BEFORE DESIGNING)

Publication *inherently* sends the redacted PDF to a third-party endpoint. That's fine — the whole point of publishing is that the document becomes public. But the route it takes matters for our trust story:

- **Acceptable:** browser → customer's GPP-publicatiebank instance, directly. No bytes touch our server.
- **Acceptable:** browser → customer's DMS / Woo-platform, directly, via their own upload API.
- **NOT acceptable:** browser → woobuddy.nl → publicatiebank. That would make us a passthrough for document content and break the "PDF verlaat nooit uw infrastructuur" claim.

The design constraint is: **our server must never see the redacted PDF**, even in flight. This likely means browser-side `fetch()` to the publicatiebank, which in turn means we need CORS on the target, or an OAuth2 device-flow style handshake where the browser holds the token.

See `docs/reference/llm-revival.md` for the analogous "local-only" constraint we applied to LLMs — the same discipline applies here.

## Scope (V1 — direct-publish from the review screen)

### Frontend

- [ ] **"Publiceer op open.overheid.nl" secondary button** in the export toolbar, alongside the #52 "Exporteer met publicatiemetadata" button. Initially hidden behind a feature flag; enable per-org once a pilot asks.
- [ ] **Publicatie-dialog** that collects endpoint + credentials on first use, stored in IndexedDB (not on the server):
  - GPP-publicatiebank base URL (e.g. `https://publicatiebank.gemeente-xxx.nl`)
  - API token or OAuth2 client-id (mechanism TBD — see Open Questions)
  - Publicatie-bundel defaults (informatiecategorie, creator) — reuse the inputs from #52
- [ ] **Publish flow:** build the DiWoo bundle client-side (reusing #52), then stream each part (redacted PDF, metadata.xml, metadata.json, redaction-log.csv) to the publicatiebank's upload endpoints directly from the browser via `fetch()`.
- [ ] **Progress + result UX:** progress bar per file, final link to the published record on open.overheid.nl (or the staging equivalent). Handle common failures clearly: CORS blocked, 401, 413 (file too large), 4xx metadata validation.
- [ ] **Audit record:** a lightweight "published at `<timestamp>` to `<endpoint>`, record id `<x>`" line appended to the per-document audit log (#19). We persist the URL and timestamp only — never the bytes.

### Backend

- [ ] **No proxy endpoint.** The backend does not route document bytes. If the browser can't reach the publicatiebank (CORS, private network), the answer is "configure your publicatiebank to accept WOO Buddy as a CORS origin" or "use the bundle download from #52 and upload manually" — not "let our server relay it."
- [ ] **Optional:** a `/api/publish/verify` endpoint that, given a published record URL, fetches the public JSON metadata and confirms the record is live. This touches only public metadata, not document bytes, so it's safe to run server-side.

### Tests

- [ ] End-to-end test against a local GPP-publicatiebank dev instance (`docker compose up publicatiebank` fixture) — upload a fixture PDF + metadata, assert the record is created and retrievable.
- [ ] Network-path assertion: in a browser test, intercept all requests during a publish and assert that no request body containing PDF bytes hits `api.woobuddy.nl` or any other WOO Buddy origin. This is the non-regression test for the client-first guarantee.
- [ ] Auth-failure UX test: bad token surfaces a clear Dutch error message with a link to the docs, not a generic 401.

## Acceptance

- A reviewer with a configured GPP-publicatiebank endpoint can publish a redacted document + DiWoo metadata in one click from the review screen
- The redacted PDF never passes through any WOO Buddy-operated server (network inspection confirms)
- Failed publishes produce clear, actionable error messages in Dutch
- The audit log records *that* and *where* a document was published, not the content
- Docs page explains the feature and the self-host requirement for CORS configuration

## Not in scope

- **Hosting a publicatiebank ourselves.** We are not in the publication-platform business. If a customer lacks a publicatiebank, point them at GPP-publicatiebank's self-host docs or a Novadoc/EntrD-style commercial partner.
- **Commercial platform connectors** (Decos, Djuma, iBabs). Each has its own API; bundle-download (#52) is the universal fallback for those. Specific connectors are separate todos under #59 (zaaksysteem connectors) if/when sold.
- **Multi-document dossier publication.** Depends on #53. V1 is single-document publishing.
- **Scheduled/automated publishing.** Out of scope — publication is an intentional act by a named reviewer; no unattended jobs.
- **DiWoo sitemap generation for a whole organization.** That's a publicatiebank responsibility, not ours.

## Open questions

- **Authentication mechanism:** GPP-publicatiebank currently expects an API token (see its OpenAPI spec). Longer-term, an OAuth2 device-flow or PKCE flow would be cleaner so the browser never handles a long-lived secret. Probe with first pilot before committing.
- **CORS reality check:** do real-world GPP-publicatiebank deployments allow browser-origin CORS from an external domain? If typically locked down to same-origin, V1 may need to run from a gemeente-hosted WOO Buddy instance (reinforcing #43 self-host). Validate before investing in the browser-direct path.
- **Does publishing open a door for us to emit a push-notification / hook back to WOO Buddy** ("your document is live, here's the URL") without breaching client-first? The publicatiebank returning a URL is fine; a callback containing document content is not. Probably moot — the browser already has the URL from the upload response.
- **Branding on open.overheid.nl:** the record metadata allows a `dcterms:publisher` and often a free-text description. Do we include *"Gelakt met WOO Buddy"* by default, offer it opt-in, or leave it off entirely? Marketing call — lean opt-in with a default of off to avoid looking like we're claiming credit for the gemeente's decision.
- **Should this be gated to the Team tier?** Arguable either way — it's a team-workflow feature in practice (someone signs off, someone publishes), but it also makes the Gratis tier a much more complete story. Default: Team-tier gated, revisit if the Gratis tier needs a stronger transparency hook.
