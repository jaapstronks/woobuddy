# 44 — Sample Documents on Landing Page (Zero-Upload Trial)

- **Priority:** P1
- **Size:** S (< 1 day)
- **Source:** Distribution & pricing strategy 2026-04
- **Depends on:** Existing `/try` and `/review/[docId]` flows
- **Blocks:** Nothing

## Why

The biggest barrier to a first trial is *upload anxiety*. A Woo-coördinator landing on the homepage for the first time is being asked to drop a real, sensitive government document into a tool they've never used. Even though our entire pitch is "uw documenten verlaten nooit uw browser," the cognitive load of the first upload is high enough that many people bounce.

A "Probeer met een voorbeelddocument" button removes that friction completely. The reviewer can experience the full loop — detection cards, click-through, redact, export — on a pre-loaded fictional Woo verzoek without committing anything. Once they've felt the value, uploading their own document is a much smaller leap.

This is a tiny piece of work with outsized impact on top-of-funnel conversion. It is the single highest-leverage marketing change we can make to the product itself.

## Scope

### Sample documents

- [ ] Generate or curate **2–3 fictional but realistic Woo documents** as PDFs, ~5–15 pages each. Cover the cases reviewers actually struggle with:
  - **Sample 1:** an e-mail thread between fictional ambtenaren — exercises e-mailheader handling, signature blocks, public-official filtering
  - **Sample 2:** a meeting verslag with an attendee list — exercises name list detection, role classification
  - **Sample 3:** a complaint letter with a citizen's name, address, BSN, IBAN — exercises Tier 1 hard identifiers
- [ ] Place under `frontend/static/samples/` — these are public, downloadable assets
- [ ] Make sure every name, address, BSN, and IBAN in the samples is provably fictional. Generate them, do not redact real ones.
- [ ] Each sample gets a short Dutch description and a thumbnail

### Landing page UI

- [ ] On the Hero or `/try` page, add a section: "Geen document bij de hand? Probeer een voorbeeld."
- [ ] Three clickable cards — thumbnail, title, one-line description, "Open voorbeeld" button
- [ ] Clicking a sample fetches the PDF from `/samples/...`, loads it into the same client-side flow as a regular upload (treat it as if the user had just dropped the file), and routes to `/review/[docId]`
- [ ] Reuse the existing IndexedDB and analyze flow — no new code paths

### Telemetry (optional, only after #41)

- [ ] Plausible event for "sample opened" with which sample
- [ ] Plausible event for "sample → real upload" conversion if measurable

## Acceptance Criteria

- 2–3 fictional sample PDFs are committed to `frontend/static/samples/`
- Landing page surfaces the samples with a clear "probeer een voorbeeld" CTA
- Clicking a sample opens it in the review flow exactly as if the user had uploaded it
- All sample data is verifiably fictional (no real names, BSNs, addresses, IBANs)

## Not in Scope

- A library of dozens of samples (start with 2–3, the highest-impact ones)
- Multilingual samples (Dutch only)
- An in-app gallery of samples after the first session
