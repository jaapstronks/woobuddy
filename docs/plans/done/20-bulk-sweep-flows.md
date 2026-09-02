# 20 — Bulk sweep flows (header block, signature block, same-name)

- **Priority:** P2
- **Size:** M (1–3 days)
- **Source:** `docs/reference/woo-redactietool-analyse.md` §"Wat moet er zwartgelakt worden?" (E-mailheaders en handtekeningblokken — "lak alles hier in één klik")
- **Depends on:** #14 (structuurherkenning — sweeps key off the `StructureSpan` output), #15 (Tier 2 card UX — the card is where same-name sweeps get triggered)
- **Blocks:** Nothing

## Why

Per-card confirmation is the right UX for ambiguous cases, but the analyse.md is blunt about the dominant case: *"E-mailheaders en handtekeningblokken — hier staat vrijwel altijd privacygevoelige informatie, en een reviewer die op elk naampje los moet klikken is stroopverven."* A single e-mailthread with five replies has ~25 header/signature detections. Each one is individually unambiguous and individually boring. A reviewer who has to accept them one by one gets bored, misses things, and blames the tool.

The fix is three targeted bulk flows, keyed off the signals we already have:

1. **Sweep a header block** — *"Lak alle persoonsgegevens in dit e-mailheaderblok."* One click accepts every detection whose span falls inside a `StructureSpan(kind="email_header")`.
2. **Sweep a signature block** — same idea for `kind="signature_block"`.
3. **Same-name sweep** — *"Lak alle voorkomens van 'Jan de Vries' in dit document."* One click on a Tier 2 card applies the same decision (accept, reject, or publiek functionaris) to every other detection with the same normalized name.

All three flows hang off existing data: the structure spans from #14, the normalized name from the name engine in #12. No new backend signals needed — this is all frontend UX.

## Scope

### 1. Sweep-this-block affordances

- [ ] When the backend returns `structure_spans` (new field on `AnalyzeResponse`, added in #14), the frontend renders a small floating chip at the top of each detected block in `PdfViewer.svelte`: *"Lak hele headerblok (5)"* / *"Lak handtekening (3)"*. The count is the number of pending detections inside the span.
- [ ] Clicking the chip runs a single undo-stack command (`SweepBlockCommand`) that accepts all pending detections inside that span. One undo reverts the whole sweep.
- [ ] The chip also appears inline next to the block in the sidebar `DetectionList.svelte` for reviewers who prefer the list over the PDF.
- [ ] Chip disappears when the block is "clean" (no pending detections left inside it).
- [ ] Publiek-functionaris detections inside a block are **not** swept — they already have a decision and a sweep must never overwrite an existing decision.

### 2. Same-name sweep from the Tier 2 card

- [ ] `Tier2Card.svelte` (whose main redesign lives in #15) grows a small link under the decision row: *"Pas toe op alle 4 voorkomens van 'Jan de Vries'"*. Only visible when the detection has an `entity_type` of `persoon` AND the name engine supplied a normalized name AND there is more than one detection with the same normalized name in the document.
- [ ] Clicking applies the *same* decision (accept / reject / publiek functionaris) to all matching detections. `SameNameSweepCommand` captures previous states for all affected detections so one undo reverts the whole set.
- [ ] If the reviewer then classifies one of those matches differently, a toast appears: *"Eerder 'Jan de Vries' gelakt onder 5.1.2e. Deze ook?"* with a one-click apply button.
- [ ] Normalization match uses the name engine's normalized form (lowercased, diacritics stripped, tussenvoegsels kept). Reviewer can't yet edit the match — exact normalized match only.

### 3. Sweep counts in the statistics bar

- [ ] The review toolbar already shows "X van Y verwerkt". Add a second line when a sweep happened: *"Laatste bulkactie: 5 headerblok items"*. Click → undo the last sweep (shorthand for Ctrl+Z targeting that command).
- [ ] When multiple sweeps pile up, the line shows the last one only; Ctrl+Z still walks the stack normally.

### 4. Keyboard shortcuts

- [ ] `Shift+H` sweeps the currently-visible header block (if any). `Shift+S` for signature block. Discoverable from the `KeyboardShortcuts.svelte` overlay.
- [ ] No shortcut for same-name sweep — too context-dependent. Stays behind the card link.

### 5. Edge cases

- [ ] A sweep in a block that contains both public-official and private-person detections must not flip the public officials. Already handled by the "skip detections that already have a decision" rule, but call it out in tests.
- [ ] A sweep command that would accept zero detections (all already clean) is a no-op — no command pushed to the undo stack.
- [ ] Same-name sweep with 50+ matches: still runs, but the confirmation dialog warns *"Dit past de beslissing toe op 50 voorkomens. Ctrl+Z maakt alles terug ongedaan."*

## Acceptance criteria

- Reviewer can sweep a header block with one click and the undo stack restores it with one Ctrl+Z.
- Reviewer can sweep a signature block the same way.
- From a Tier 2 card, reviewer can apply the same decision to all matching names in the document.
- Sweeps never overwrite detections that already have a `rejected` / `auto_accepted` / `publiek_functionaris` decision.
- Sweep chips disappear when the block has no pending items left.
- `SweepBlockCommand` and `SameNameSweepCommand` are covered by undo-stack unit tests that verify forward/reverse produce the expected state.

## Not in scope

- **Multi-document sweep.** *"Same name across all documents in the workspace"* requires auth + organizations; not now.
- **Sweep that creates new detections.** A sweep never detects — it only acts on existing detections. Detection stays in the analyze pipeline.
- **Custom sweep rules.** *"Accept every detection tagged `telefoonnummer` in Tier 1"* is covered by the existing Tier 1 auto-accept, not by a user-defined rule.
- **Aanhef (salutation) sweeps.** A salutation contains one name — there's nothing to sweep. The card's same-name link covers the cross-document case.

## Files likely to change

- `frontend/src/lib/components/review/PdfViewer.svelte` (block chips overlay)
- `frontend/src/lib/components/review/DetectionList.svelte` (sidebar chip rendering)
- `frontend/src/lib/components/review/Tier2Card.svelte` (same-name link — coordinate with #15)
- `frontend/src/lib/components/review/KeyboardShortcuts.svelte` (new shortcuts + help text)
- `frontend/src/lib/stores/undo.svelte.ts` (`SweepBlockCommand`, `SameNameSweepCommand`)
- `frontend/src/lib/stores/detections.svelte.ts` (batch review helper)
- `frontend/src/routes/review/[docId]/+page.svelte` (handlers)
- `frontend/src/lib/types/index.ts` (if `StructureSpan` type needs cross-file visibility)

## As built (2026-04-14)

Shipped this shape — note where it diverges from the original spec:

- **Backend change (contrary to "no new backend signals"):** detections need
  char offsets on the frontend to match them against structure spans, and
  that information wasn't being persisted. Added nullable `start_char` /
  `end_char` columns to the `Detection` ORM model and plumbed them through
  `PipelineDetection` → `analyze.py` row creation → `DetectionResponse`.
  Without this the sidebar has no way to ask "which detections fall inside
  this block?" — every containment check was guaranteed false. Existing
  dev DBs that predate this change need to be recreated (the project uses
  `Base.metadata.create_all`, no alembic migrations).
- **Adjacent bug fix:** while wiring the new columns in `analyze.py`,
  noticed `subject_role` (pre-filled by the #13 role engine on the
  pipeline detection) was not being forwarded to the stored Detection
  row. Added alongside the offsets so the rule engine's classification
  actually reaches the sidebar.
- **Structure-spans cache in sessionStorage:** `structureSpansStore`
  caches the analyze response's `structure_spans` keyed by document id.
  Analyze isn't re-run on soft reload, so without this the sweep chips
  would vanish after Cmd-R. Cleared on doc switch, survives reload.
- **Same-name sweep decision is fixed to "accept"** in the current
  handler. The original spec said "apply the reviewer's decision
  (accept / reject / publiek functionaris)" — in practice the link is
  only rendered on pending cards and fires before any chip is clicked,
  so there's no "reviewer's decision" to forward yet. Wiring this to
  the role chips or a two-step confirm is a follow-up.

Deferred from this ticket (still valuable, not blocking):

- **PdfViewer overlay chips.** The sidebar chips cover the "I'm scanning
  the list" workflow. Floating chips anchored over each block in the PDF
  require char-offset → page/bbox mapping that we don't have on the
  viewer side yet (the bbox index is page-indexed, not char-indexed).
  Worth a small follow-up ticket once #14 exposes per-span bboxes.
- **"Laatste bulkactie: N headerblok items" stats-bar line.** The undo
  store records the label on every command, but the stats bar doesn't
  yet surface a callout for the most recent one. Pure UI work, no new
  data. Follow-up ticket.
- **Same-name warning toast when the reviewer classifies a match
  differently later.** Needs an additional state machine on the
  detection store (remember past sweep targets); deferred until there's
  evidence reviewers want it.
- **50+ matches confirmation dialog.** The current same-name link
  performs the sweep immediately. In practice 50+ matches is rare and
  Ctrl+Z is the safety net. Add a confirmation step if/when reviewers
  report accidental bulk accepts.

Tests: `SweepBlockCommand` and `SameNameSweepCommand` covered by
`frontend/src/lib/stores/undo.svelte.test.ts`. `groupDetectionsBySpan`,
`detectionInsideSpan`, `normalizeDetectionName`, and
`findSameNameDetections` covered by
`frontend/src/lib/utils/structure-matching.test.ts`. All 72 frontend
tests pass; `npm run check` is clean.
