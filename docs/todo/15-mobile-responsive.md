# 32 — Mobile Responsive Polish

- **Priority:** P3
- **Size:** S (< 1 day)
- **Source:** Testing & Polish briefing, Section 7
- **Depends on:** Nothing
- **Blocks:** Nothing

## Why

Landing page, auth pages, dashboard, and billing must work on mobile. The review interface is desktop-only by nature (two-column PDF + sidebar, precise mouse interaction).

## Scope

### Mobile-friendly pages

- [ ] Landing page: fully responsive, single column on small screens
- [ ] Auth pages (login, signup): simple forms, work on any screen
- [ ] Dashboard / dossier list: card layout adapts to screen width
- [ ] Billing + org settings: form-based, standard responsive

### Desktop-only pages

- [ ] Review interface: `min-width: 1024px` on container
- [ ] Below 1024px: show message "De beoordelingsinterface is geoptimaliseerd voor desktop" with link to read-only dossier view
- [ ] Edit mode: desktop-only (precise mouse control required)
- [ ] Redaction log: desktop-only (complex table)

### Implementation

- [ ] Tailwind responsive breakpoints throughout
- [ ] Test key pages at 375px, 768px, 1024px, and 1440px widths

## Acceptance Criteria

- Landing page looks good on iPhone/Android screens
- Auth and dashboard are usable on mobile
- Review interface shows a clear desktop-only message on small screens
