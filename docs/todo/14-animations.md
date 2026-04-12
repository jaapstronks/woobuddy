# 31 — Landing Page Animations

- **Priority:** P3
- **Size:** S (< 1 day)
- **Source:** Testing & Polish briefing, Section 2
- **Depends on:** Nothing
- **Blocks:** Nothing

## Why

The landing page is the first impression. Subtle animations make it feel polished and professional. The app interface should NOT be animated (speed > prettiness when reviewing 200 detections).

## Scope

### Landing page

- [ ] Hero section: staggered fade-and-slide-up entrance (tagline, description, upload area) — CSS transitions or `@humanspeak/svelte-motion`
- [ ] Upload zone: breathing pulse CSS animation on border, scale-up on drag-over
- [ ] "Hoe werkt het?" steps: scroll-reveal with stagger via IntersectionObserver
- [ ] Entity type cards: same scroll-reveal pattern

### App interface (minimal)

- [ ] Detection card accept/reject: brief green/red flash (200ms CSS transition)
- [ ] Mode toggle: toolbar indicator pulse (100ms background transition)
- [ ] Progress bar: `transition: width 0.3s ease`

### Accessibility

- [ ] `@media (prefers-reduced-motion: reduce)` disables all animations
- [ ] No animation in data tables, PDF viewer, or sidebar scrolling

## Acceptance Criteria

- Landing page feels polished with smooth entrance animations
- App interface has minimal, fast micro-feedback
- All animations respect `prefers-reduced-motion`
