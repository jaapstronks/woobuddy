# 16 — Document Lifecycle (Draft / Approve / Reopen)

- **Priority:** P1
- **Size:** M (1–3 days)
- **Source:** Draft Workflow briefing, "The Draft Workflow" + "Document-level approval" sections
- **Depends on:** #00 (Client-first architecture), #24 (Auth — approval needs to know who approved)
- **Blocks:** #18 (Draft preview), #20 (Export versioning), #21 (Concept export)

## Why

Currently documents go from "review" straight to "exported" with no formal approval step. In real Woo practice, a redacted document is a living draft until formally finalized. The approval gate prevents accidental publication of incomplete work.

Under client-first architecture, document lifecycle states are tracked server-side (metadata), but the PDF itself lives only in the browser. The "draft preview" is rendered client-side from the local PDF + server-side detection metadata.

## Scope

### Extended document status enum

- [ ] Add `draft` status between `review` and `approved`
- [ ] Full lifecycle: `uploaded → processing → review → draft → approved → exported`
- [ ] Document enters "draft" when all detections are addressed

### Approval flow

- [ ] "Goedkeuren" (Approve) button on document — runs completeness check:
  - All pages marked as reviewed (depends on #10, can be stubbed initially)
  - All Tier 2 detections resolved (no "concept" status)
  - All Tier 3 annotations resolved
  - All draft comments resolved (when implemented)
  - Five-year rule warnings acknowledged
- [ ] If checks pass → status moves to "approved", document becomes read-only
- [ ] If checks fail → dialog lists exactly what's still open, with clickable links to each item

### Reopening

- [ ] "Heropenen" button on approved documents
- [ ] Confirmation dialog (Dutch): explains the document needs re-approval after changes
- [ ] Status reverts to "draft"
- [ ] Audit log: who reopened, when, optional reason field — no content
- [ ] Invalidates any current export metadata (see #20). Under client-first, there's no stored export to invalidate — just the metadata record.

### Visual lifecycle indicator

- [ ] `<DocumentLifecycle>` component — shows where the document is in its lifecycle
- [ ] Compact visual (status badge or step indicator) on document cards and review page

### API endpoints

- [ ] `POST /api/documents/:id/approve` — runs completeness check, transitions status
- [ ] `POST /api/documents/:id/reopen` — reverts to draft with audit entry

## Acceptance Criteria

- Document transitions through the full lifecycle
- Cannot approve with unresolved detections — dialog lists blocking items
- Approved document is read-only (edit buttons disabled)
- Reopening requires confirmation and creates an audit entry
- Lifecycle status is visible on document cards

## Not in Scope

- Dossier-level approval (all docs approved → dossier approved)
- Formal sign-off workflow with multiple approvers
