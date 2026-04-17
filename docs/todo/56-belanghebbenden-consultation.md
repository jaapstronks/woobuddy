# 56 — Belanghebbenden-consultation workflow (Woo art. 4.4)

- **Priority:** P2 (post-signal, Phase F)
- **Size:** M (1–3 days)
- **Source:** Competitor landscape 2026-04 — INDICA ships this; required by Woo art. 4.4
- **Depends on:** #32 (auth), #33 (organizations), #53 (dossier mode), #25 (document lifecycle)
- **Blocks:** Nothing

## Why

Woo **artikel 4.4** requires that before publishing information that concerns a third party (e.g. a business partner named in emails, a citizen whose data appears, a subsidized organization), the bestuursorgaan must give that third party the opportunity to respond — the *zienswijze* stage. The consultation can lead to the party requesting additional redactions, a delay, or in rare cases a rechterlijke beoordeling.

Without tooling, this is a manual process: the reviewer copies passages into an email, sends it to the belanghebbende, files the response somewhere, and manually reflects their input in the redactions. INDICA automates this: identify passages referring to a specific third party, generate a consultation packet, track responses, apply outcome back to the dossier.

WOO Buddy today has no concept of a belanghebbende. Adding this closes a compliance gap that enterprise buyers will check for in a feature matrix, and it's a natural team-tier feature because it's multi-user by nature (reviewer coordinates with an external third party over time).

## Scope

### Data model

- [ ] New concept `Belanghebbende` (per-dossier): `{id, dossier_id, name, email, organization, notes, status: 'not_contacted' | 'awaiting_response' | 'responded' | 'overridden'}`
- [ ] New `BelanghebbendeConsultation` linking a belanghebbende to N detections or document regions: *"dit zijn de passages waarover X is geraadpleegd"*
- [ ] New `ConsultationResponse` capturing the third party's input: *"X wil ook deze passage gelakt"* (free text + optional proposed additional redactions).

### Workflow

- [ ] **Identify belanghebbenden**: from the per-document detections tagged as entity type `organisatie` or `derde partij`, offer a "add as belanghebbende" action.
- [ ] **Group passages by belanghebbende**: on the dossier overview, a panel "Te raadplegen belanghebbenden" listing each party and the passages about them.
- [ ] **Generate consultation packet** per belanghebbende:
  - A PDF extract showing the passages in context (with surrounding paragraph, with personal data of other persons redacted).
  - A cover letter template in Dutch explaining the consultation, citing art. 4.4, giving a response deadline (default 2 weeks, configurable per dossier), and asking for zienswijze.
  - Output as zip bundle; reviewer sends via email/post themselves.
- [ ] **Response capture**: reviewer pastes/uploads the zienswijze into the tool, flags status `responded`. Any proposed extra redactions are added as pending detections for reviewer confirmation.
- [ ] **Override path**: reviewer can set status `overridden` with a required justification (e.g. *"reactietermijn verstreken, art. 4.4 vijfde lid"*) which lands in the audit log (#19).
- [ ] **Block-publication gate**: dossier cannot move to `ready_for_publication` status while any belanghebbende has status `awaiting_response`, unless overridden with justification.

### Reporting

- [ ] Consultation log export: a CSV/PDF record of every belanghebbende, their status, response, and the reviewer's resolution — lands alongside the redaction inventory in the publication bundle (#52).
- [ ] Dossier-level audit log (#19 extension) shows consultation events.

### Privacy considerations

- [ ] Belanghebbenden-emailadressen are personal data — stored on the server only for authenticated dossiers, never for anonymous paths.
- [ ] The consultation packet is generated **client-side** from the existing dossier PDFs; it doesn't require a new server-side PDF-handling path.
- [ ] Responses are free text typed by the reviewer — no inbound email integration at V1 (would require SMTP intake, DPA, etc.). Reviewer copies from their normal email client.

### Tests

- [ ] Unit: generating a consultation packet produces the expected passage extracts with non-belanghebbende personal data redacted
- [ ] Integration: creating a belanghebbende → generating packet → capturing response → status transitions to `responded` → dossier moves to `ready_for_publication`
- [ ] Block test: dossier cannot publish while a belanghebbende has `awaiting_response` and no override

## Acceptance

- Reviewer can register belanghebbenden against a dossier, associate them with specific passages, generate consultation packets, capture responses, and see status tracked dossier-wide
- Dossier publication is gated on consultation completion or explicit override with justification
- Consultation log appears in the publication bundle and audit trail
- Belanghebbenden-data is org-scoped and never leaks to other organizations

## Not in scope

- Inbound email integration (receive zienswijzen automatically) — nice-to-have, out of V1
- Belanghebbenden-portal where the third party logs in to respond — significantly bigger scope, only build if a pilot explicitly asks
- Automated detection of "who is a belanghebbende" — reviewer decides; we help them organize
- Legal-document template library beyond the default Dutch art. 4.4 cover letter — pilots can customize; full template engine is out of V1

## Open questions

- Default response deadline: 2 weeks matches common Dutch practice. Make configurable per dossier.
- Does the audit log flag "consulted but no response received and deadline expired" clearly to the publisher? Recommendation: yes, with a visible warning on the dossier overview.
