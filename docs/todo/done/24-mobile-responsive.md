# 24 — Mobile Responsive Polish

- **Priority:** P3
- **Size:** S (< 1 day)
- **Source:** Testing & Polish briefing, Section 7
- **Depends on:** Nothing
- **Blocks:** Nothing
- **Status:** Done (2026-04-14)

## Why

The marketing surface (landing page) and the trial entry point (`/try`) must work on mobile — that's where new users land. The review interface is desktop-only by nature: two-column PDF + sidebar layout, pixel-precise boundary editing with the mouse, and keyboard-driven review shortcuts.

## What was built

### Mobile-friendly pages — already responsive, verified

- **`/` landing**: hero, HowItWorks, WhatWeDetect, YouDecide, OpenSource, Footer all use Tailwind responsive classes (`sm:`, `md:`, `lg:`) and stack to a single column on small screens. No changes needed.
- **`/try` upload**: form-based layout with `max-w-2xl`, `sm:text-5xl` heading, FileUpload that adapts to width. No changes needed.

### Desktop-only gate — added

`frontend/src/routes/review/+layout.svelte` now renders a Dutch fallback below the Tailwind `lg` breakpoint (1024px) and shows the actual review children only at `lg` and up. This single layout change covers both child routes:

- `/review/[docId]` (review interface)
- `/review/[docId]/log` (redaction log — complex table, also unfit for mobile)

The fallback shows the WOO Buddy logo, a Monitor icon, the message "Beoordelen werkt het beste op desktop" with the explicit "minimaal 1024 pixels" requirement, and a "Terug naar start" CTA back to `/`. It does NOT link to a "read-only dossier view" because no such view exists in the current single-document architecture (the original briefing was written before the multi-document scope was dropped).

### Auth / dashboard / billing pages

Out of scope: these routes do not exist yet. The project is currently single-document with no auth flow, no dossier list, and no billing surface. When those routes land they should be built mobile-first from day one.

## Verified

Tested with Playwright at the breakpoints called out in the briefing:

- **375 × 812** (iPhone): landing hero, HowItWorks single-column, `/try` upload form, review gated, log gated
- **768 × 1024** (tablet): `/try` upload form, review gated
- **1023 × 800**: review gated (boundary check, just below `lg`)
- **1024 × 800**: review interface renders desktop layout

## Acceptance Criteria

- ✅ Landing page looks good on iPhone/Android screens
- ✅ `/try` upload flow is usable on mobile (replaces the original "auth and dashboard are usable on mobile" check, since those routes don't exist yet)
- ✅ Review interface shows a clear desktop-only message on small screens, gated at the layout level so any future review sub-route inherits it
