# 23 — Landing Page Animations

- **Priority:** P3
- **Size:** S (< 1 day)
- **Source:** Testing & Polish briefing, Section 2
- **Status:** Done (2026-04)

## Why

The landing page is the first impression. Subtle animations make it feel polished and professional. The app interface should NOT be animated (speed > prettiness when reviewing 200 detections).

## What was built

### Motion primitives — `frontend/src/app.css`

- `.fade-in-up` — pure CSS entrance animation (700ms, easing
  `cubic-bezier(0.22, 1, 0.36, 1)`), used by the hero so it fires immediately
  on hydration without waiting for a scroll event.
- `.reveal` + `.is-visible` — opacity/translate transition driven by an
  `IntersectionObserver` action. Pair with `use:reveal` to have a node fade up
  the first time it enters the viewport, with optional `delay` for staggers.
- `@keyframes breathe-pulse` — soft halo for the upload drop zone.
- `@keyframes mode-toggle-pulse` — one-shot background flash for the
  review/edit mode toggle in the PDF viewer toolbar.

### Reveal action — `frontend/src/lib/actions/reveal.ts`

`use:reveal={{ delay: 90 }}` adds `is-visible` once the node intersects the
viewport, then disconnects. Honours `prefers-reduced-motion: reduce` by
short-circuiting and revealing immediately. SSR-safe (the action only runs on
the client).

### Landing page

- **Hero (`Hero.svelte`)** — eyebrow, headline, paragraph, chip list and CTA
  row are staggered `fade-in-up` (delays 0/80/200/320/440 ms).
- **HowItWorks** — heading + each of the four step cards reveal in sequence
  (delay `i * 90`).
- **WhatWeDetect** — heading + each entity card reveal (delay `i * 70`).
- **YouDecide** — heading + each tier card reveal (delay `i * 110`).
- **OpenSource** — heading + Wel/Niet columns + GitHub call-to-action all
  reveal (the Niet column is offset by 120 ms for a one-step stagger).

### Upload zone (`FileUpload.svelte`)

- Continuous `breathe-pulse` halo while idle.
- Switches to `border-primary bg-primary-soft scale-[1.015]` while a file is
  being dragged over the zone (the breathing pulse is dropped during drag so
  the static drag state is unambiguous).

### App interface (kept minimal, deliberately)

- **Mode toggle** (`PdfViewer.svelte`) — `.mode-btn-active` runs the new
  `mode-toggle-pulse` keyframe (220 ms, ease-out) each time it acquires the
  active class, giving a brief background flash on mode change.
- **Progress bar** — Shoelace's `sl-progress-bar` already animates `value`
  changes by default; no override needed.
- **Detection card accept/reject flash** — intentionally not implemented.
  The card components (Tier1/Tier2/Tier3) don't currently track per-item
  decision moments, and threading a transient "just-decided" flag through
  the existing accept/reject handlers would have meant touching the review
  store and three card components for a P3 effect. The cards already have
  hover transitions and the reviewer gets immediate feedback from the card
  disappearing/changing tier. Revisit if usability testing flags it.

### Accessibility

- A single `@media (prefers-reduced-motion: reduce)` block in `app.css`
  collapses every motion primitive (`.reveal`, `.fade-in-up`,
  `.breathe-pulse`) to its resting state and clears any inline transition
  delays the reveal action applied for staggering.
- `PdfViewer.svelte` has its own scoped reduced-motion override for
  `.mode-btn` / `.mode-btn-active`.
- The reveal action also checks `prefers-reduced-motion` in JS and skips
  the IntersectionObserver entirely, so users with reduced motion get
  content immediately on hydration with no observer churn.

## Acceptance Criteria — met

- [x] Landing page feels polished with smooth entrance animations
- [x] App interface has minimal, fast micro-feedback (mode toggle pulse only;
      progress bar already smooth; card flash deliberately deferred — see
      above)
- [x] All animations respect `prefers-reduced-motion`
