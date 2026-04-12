# 30 — Loading States & Skeleton Screens

- **Priority:** P2
- **Size:** M (1–3 days)
- **Source:** Testing & Polish briefing, Section 6
- **Depends on:** Nothing
- **Blocks:** Nothing

## Why

The review interface loads complex data (PDF, detections, metadata). Without proper loading states, users see blank screens or layout shifts that feel broken.

## Scope

### Open PDF → analyze (client-first flow)

- [ ] Multi-step progress indicator: PDF laden → Tekst extraheren (client) → Analyse verzenden → Detectie → Classificatie
- [ ] Text extraction step happens client-side (pdf.js) — show progress per page
- [ ] Analysis step sends extracted text to server — show indeterminate progress
- [ ] Each step transitions: empty circle → active/indeterminate → checkmark
- [ ] Use Shoelace `<sl-progress-bar>` with indeterminate/determinate modes

### Review interface initial load

- [ ] Skeleton PDF page: gray rectangle with faint line placeholders
- [ ] Skeleton detection cards: 3-4 gray placeholder cards with shimmer animation
- [ ] Toolbar loads immediately with zero state

### Long operations (>500ms)

- [ ] Detection pipeline (10-60s): full progress screen
- [ ] Export generation (5-30s): progress bar in export dialog
- [ ] Batch operations (1-5s): inline spinner, disabled button state
- [ ] LLM classification (1-2s): subtle spinner on the detection card

## Acceptance Criteria

- No blank screens during data loading
- Processing shows clear step-by-step progress
- Skeleton screens match the layout of actual content (no layout shift)
- Long operations show appropriate feedback
