# 54 — Cross-document deduplication

- **Priority:** P2
- **Size:** M (1–3 days)
- **Source:** Competitor landscape 2026-04 — INDICA and Novadoc both lead with "we found 40% duplicates in your Woo-besluit"
- **Depends on:** #53 (dossier mode)
- **Blocks:** Nothing

## Why

A real Woo-besluit often contains the same email thread attached to 20 different documents, the same beleidsnota referenced in 15 memo's, or the same scan'd stuk showing up in both the email en de handmatig toegevoegde bijlage. Reviewing all of them from scratch is a massive waste. Every serious competitor detects these duplicates up front and lets the reviewer decide whether to skip, hide, or redact once-and-propagate.

Because WOO Buddy is client-first, the dedup happens in the browser — we hash each PDF (and each page) locally and compare in IndexedDB. No document bytes leave the device.

## Scope

### Client-side hashing

- [ ] When a PDF is added to a dossier, compute:
  - **Whole-document SHA-256** from the raw bytes — exact duplicates (same file uploaded twice).
  - **Per-page content hash** from the text extracted by pdf.js `getTextContent()` — near-duplicates where the container differs but the content matches (e.g. same email saved as two PDFs with different headers).
  - **Fuzzy content signature** (MinHash or simhash over text shingles) for "this email is 95% the same as that one" — catches reply chains where the only difference is the added `On ... wrote:` block.
- [ ] Hashes stored in IndexedDB keyed by `{dossierId, docId, pageIndex}`. No hashes ever sent to the server.

### UX

- [ ] **Duplicate overview panel** in the dossier screen: a collapsible section "Dubbele of vrijwel identieke documenten (N)" listing clusters:
  - Exact dups grouped under one row with "3 identieke kopieën" and links to each.
  - Near-dups shown as "Lijkt voor 95% op [andere-doc].pdf" with a diff preview.
- [ ] **Per-cluster actions**:
  - "Verberg duplicaten — behandel alleen het eerste" (cluster reduced to representative, rest marked `hidden` and excluded from export)
  - "Pas redacties van [doc] toe op alle duplicaten" (one-click apply; creates `Detection` records on the others mapping to the same bbox coordinates)
  - "Behandel apart" (no-op, cluster dismissed)
- [ ] **Dossier-level detection-count badge** updates to reflect hidden documents: "42 documenten (12 verborgen als duplicaat)".
- [ ] **Export**: hidden duplicates excluded from the export zip by default; toggle "include duplicates in export for transparency" for cases where the publisher wants to disclose the duplication to the verzoeker.

### Per-page dedup (stretch)

- [ ] For near-dup clusters where only some pages differ (e.g. an email plus its attachment vs the same email standalone), highlight the differing pages and let the reviewer review only those.

### Tests

- [ ] Unit: exact-duplicate detection catches byte-identical PDFs
- [ ] Unit: near-duplicate detection catches same-text-different-metadata PDFs (common Outlook quirk)
- [ ] Unit: MinHash similarity is stable (small text changes don't drop similarity below threshold; different docs don't cross threshold)
- [ ] Integration: a dossier with 10 docs including 3 exact dups and 2 near-dups produces the expected clusters
- [ ] Network-isolation: zero outbound requests during the dedup phase

## Acceptance

- Uploading multiple documents into a dossier automatically clusters exact and near-duplicate documents
- Reviewer can hide duplicates or propagate redactions from one document across a cluster
- Export respects the hide decisions
- All dedup computation happens in the browser — verified by network-isolation test
- UI honestly reports dedup results: false-positive clusters can always be dismissed, never forced-hidden

## Not in scope

- Cross-dossier dedup (a document reused between two separate Woo-verzoeken) — privacy implications, out of V1
- Binary-similar PDF detection for scanned PDFs without usable text (would need image-similarity; depends on OCR output from #49)
- AI-based semantic dedup ("these two emails say the same thing in different words") — out of scope per the no-LLM rule

## Open questions

- Similarity threshold for "near-duplicate" — start at 0.9 MinHash similarity, make it configurable in developer settings, surface in the UI once we have pilot feedback
- How do we visualize the diff inside a near-dup cluster? A side-by-side text diff is the obvious V1 — implement with `diff` library, lazy-loaded
