# 55 — Cross-document name propagation

- **Priority:** P2
- **Size:** M (1–3 days)
- **Source:** Competitor landscape 2026-04 — core team-tier value proposition; saves hours on typical "emails of person X" Woo-verzoeken
- **Depends on:** #53 (dossier mode), #21 (per-document custom wordlist — already done)
- **Blocks:** Nothing

## Why

The most common Woo-verzoek shape is *"alle correspondentie van persoon X over onderwerp Y tussen datum Z1 en Z2"*. That means the same name (and the same public-official reference list) shows up in every document of the dossier.

Today the reviewer has to confirm Jan Jansen as a person in every single document — even though they already made that decision on document 1. This is the single most obvious "we're making you do the same work 40 times" pain in a multi-document review. Fixing it is cheap once dossier mode exists.

This todo extends #21's per-document wordlist concept to the dossier level: a decision made once applies to every document in the dossier (with an explicit override per document).

## Scope

### Dossier-level decision store

- [ ] New client-side (IndexedDB-backed) structure `DossierDecisionStore` holding:
  - **Confirmed entities**: `[{entity_text, entity_type, decision: 'redact' | 'keep', article?: string, scope: 'all' | 'document'}]`
  - **Public-official list**: `[{entity_text, role, reason}]` (extends #17's per-document list to dossier level)
  - **Custom wordlist**: `[{term, tier, article?, case_sensitive?}]` (extends #21 to dossier level)
- [ ] Each decision records `scope: 'all'` (propagate) or `scope: 'document'` (this doc only). `'all'` is the default when the reviewer checks a "binnen dit dossier onthouden" toggle on the suggestion card.

### Propagation logic

- [ ] When a detection is confirmed or rejected on document A with `scope: 'all'`, the decision is replayed on every other document in the dossier:
  - For each other document, find all detections with matching `entity_text` (normalized — Dutch name particles, case-insensitive, diacritic-insensitive) and apply the same decision.
  - For documents not yet analyzed, the decision is stored and applied automatically when analysis runs.
- [ ] **Manual addition propagation**: if the reviewer adds "Marie van der Berg" via area-selection or custom-wordlist, searching across the whole dossier happens once, and all matches become auto-redacted in every document.
- [ ] **Override**: per-document toggle "deze persoon overschrijven in dit document" that creates a document-scoped decision shadowing the dossier-level one. Rare, but required — e.g. same name belongs to two different people across documents.

### UX

- [ ] **Suggestion card** (#15) gains a checkbox "Onthoud dit besluit voor het hele dossier" — defaults to checked in dossier mode, unchecked in single-doc mode.
- [ ] **Dossier decision panel** on the dossier overview: "Besluiten die voor alle documenten gelden" — a scannable list of dossier-level decisions with counts ("Jan Jansen — 47 keer gelakt in 12 documenten") and an un-propagate button per row.
- [ ] **Diff badge** on per-document view: "3 besluiten van dit dossier zijn op dit document toegepast" with a link to the dossier decision panel.
- [ ] **First-time reviewer copy** on the dossier overview: *"Een besluit dat u hier maakt, geldt automatisch voor alle documenten in dit dossier. U kunt per document afwijken als dat nodig is."*

### Server-side (post-auth only)

- [ ] Dossier-level decisions persisted alongside the dossier (depends on #53 schema). Anonymous path keeps them in IndexedDB only.
- [ ] API: `POST /api/dossiers/:id/decisions` for bulk create, `PATCH` for update, `DELETE` for un-propagate.

### Tests

- [ ] Unit: confirming an entity with `scope: 'all'` in document A creates matching confirmations in already-analyzed documents B and C
- [ ] Unit: adding a document to an existing dossier automatically applies existing dossier-level decisions to the new document's detections
- [ ] Unit: per-document override correctly shadows dossier-level decision
- [ ] Unit: normalized matching handles Dutch name particles ("van der", "de", "'t") and case/diacritic variation
- [ ] Integration: reviewer confirms "Jan Jansen" once in doc 1 of a 40-doc dossier; all 40 docs show Jan Jansen pre-confirmed for redaction

## Acceptance

- Reviewer reviewing a 40-document dossier confirms each named person once, not 40 times
- Dossier decision panel shows all propagated decisions with counts and lets the reviewer un-propagate
- Per-document override exists for the rare case two people share a name across documents
- Decision propagation is instant (<100ms for a typical 40-doc dossier)
- Anonymous dossiers keep decisions in IndexedDB; zero network traffic for decision propagation on the anonymous path

## Not in scope

- Fuzzy name matching (Dutch patronyms, stemming) beyond basic normalization — revisit if pilots ask
- Cross-dossier decisions ("always redact Jan Jansen for this organization") — that's an organization-level wordlist, belongs to the Team-tier feature set, tracked implicitly via #21
- Semantic propagation ("this text is *about* Jan even though his name isn't here") — explicitly out of scope per no-LLM rule

## Open questions

- Should rejected-decisions also propagate (i.e. "this person is a public official, do not redact")? Yes, same mechanism, same `scope: 'all'` toggle. It's the public-official list functionally.
- Does propagation honor the suggestion card's "confirmed" vs "auto-applied" distinction? Recommendation: propagated decisions are marked as auto-applied on target documents, visually identical to Tier 1 detections. The audit log (#19) shows "propagated from [source doc]" so provenance is clear.
