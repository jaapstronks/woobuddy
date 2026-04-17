# 58 — Woo-jaarverslag / reporting dashboard

- **Priority:** P3
- **Size:** M (1–3 days)
- **Source:** Competitor landscape 2026-04 — Novadoc ships this; gemeenten need yearly Woo-jaarverslag numbers
- **Depends on:** #19 (redaction log — done), #33 (organizations), #53 (dossier mode)
- **Blocks:** Nothing

## Why

Dutch gemeenten are required to publish a yearly Woo-jaarverslag that includes quantitative stats: number of verzoeken received, average processing time, verzoeken per onderwerp, most-frequently-cited weigeringsgronden, etc. Today these numbers come from whatever zaaksysteem tracks the verzoeken, and tooling-level stats (how many passages were redacted, under which grond, how often did we suggest vs confirm) are typically unavailable.

Novadoc markets "dat alle gegevens van de zaken blijven bestaan, zodat er eenvoudig rapportages samengesteld kunnen worden voor onder andere jaarverslagen." It's a soft feature — it doesn't win deals — but it sticks reviewers to the product (they build their yearly rhythm around it) and gives the Woo-coördinator a compelling reason to evangelize WOO Buddy internally.

Because everything lives in the audit log already (#19), building a dashboard is mostly aggregation + chart rendering.

## Scope

### Data

- [ ] Queries over existing `RedactionLogEntry` + `Dossier` + `Document` tables scoped per organization
- [ ] No new tables — all metrics derived from the audit log

### Dashboard views

- [ ] **Overview**: KPIs for a user-selected timeframe (default: current calendar year)
  - Total dossiers processed
  - Total documents reviewed
  - Total redactions applied, broken down by Tier 1 / 2 / 3
  - Average processing time per dossier (first upload → published)
- [ ] **Redaction grounds breakdown**: bar chart of Woo-artikelen cited most often, filterable by tier
- [ ] **Reviewer activity** (per-org, anonymized by default — individual view behind role/permission from #34): documents reviewed per reviewer per month
- [ ] **Detection quality**: suggested vs confirmed vs rejected per entity type, month-over-month. A surfaced drop in confirmation rate is an early warning that the rule-based detection needs tuning.
- [ ] **Export**: CSV + PDF of the selected view, formatted for inclusion in a jaarverslag document

### UX

- [ ] New route `/org/reports` (auth-gated, admin-role only)
- [ ] Date-range picker, org-scope selector (once #33 supports multi-org users)
- [ ] Charts rendered client-side with a lightweight library (Chart.js or Observable Plot — no d3-sized dependency)
- [ ] Export button produces CSV via existing patterns + PDF via `pdfmake` (already in dep tree from #46)

### Privacy

- [ ] Reports aggregate metadata only — **never** surface document content, entity text, or belanghebbende names in charts or exports
- [ ] Reviewer-level stats can be hidden by org policy (for organizations where reviewer performance metrics are sensitive under works-council/OR agreements)

### Tests

- [ ] Aggregation queries produce correct counts on fixture data
- [ ] Exports include only aggregated numbers, not entity text
- [ ] Role-gated: non-admin users see a 403

## Acceptance

- Admin user can view a year-over-year overview of redaction activity for their organization
- Charts load quickly (<2s) on a dataset of 1000 dossiers
- Exports are jaarverslag-ready (CSV for further analysis, PDF for copy-paste into a Word document)
- Per-reviewer stats can be disabled org-wide via a settings toggle

## Not in scope

- External BI integration (Power BI, Tableau) — CSV export is enough for V1
- Cross-organization benchmarking ("your gemeente vs the average") — raises privacy concerns, out of V1
- Predictive analytics ("expected volume next month") — out of scope per no-LLM rule
- Verzoeker-facing reports — the publisher chooses what to publish; we don't auto-publish stats

## Open questions

- Include zaaksysteem data (actual Woo-verzoek intake dates, not just WOO Buddy upload times) via connector from #59? If integrations exist, yes — enriches the "average processing time" metric significantly. V1 uses WOO Buddy timestamps only.
- Default retention period for audit-log data — likely whatever is set in the Verwerkersovereenkomst. Make configurable.
