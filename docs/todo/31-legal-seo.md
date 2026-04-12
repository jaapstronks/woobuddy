# 28 — Legal Pages & SEO

- **Priority:** P2
- **Size:** S (< 1 day)
- **Source:** Testing & Polish briefing, Sections 10 (SEO) + (Legal pages)
- **Depends on:** Nothing
- **Blocks:** Nothing (but required before public launch)

## Why

A Dutch SaaS product processing government documents needs legal pages. Government organizations will want a data processing agreement before uploading real documents. SEO ensures the tool is discoverable.

## Scope

### Legal pages

- [ ] `/privacy` — Privacyverklaring (what data, how processed, retention, access). **Key point under client-first:** emphasize that PDFs never leave the browser, no document content is stored on the server, and text analysis is ephemeral. This dramatically simplifies the privacy story.
- [ ] `/terms` — Algemene voorwaarden (usage terms, liability, SLA)
- [ ] `/cookies` — Cookie policy (minimal: session cookies only, no tracking)
- [ ] `/verwerkersovereenkomst` — Data processing agreement template. **Simpler under client-first:** the DPA scope is limited to user account data and detection metadata (positions, types, articles) — not document content. This reduces procurement friction significantly.
- [ ] All pages in Dutch, simple markdown-rendered
- [ ] Footer links to all legal pages

### SEO meta tags (landing page)

- [ ] `<title>` — "WOO Buddy — Jouw slimme assistent voor het lakken van Woo-documenten"
- [ ] `<meta name="description">` — Dutch description of the tool
- [ ] Open Graph tags: `og:title`, `og:description`, `og:image`, `og:url`
- [ ] Twitter card: `summary_large_image`
- [ ] Create `og-image.png` (1200x630px) — logo, tagline, stylized screenshot

### Favicon

- [ ] Generate favicon set from logo: favicon.ico, apple-touch-icon, 32x32, 16x16
- [ ] Place in `static/`

### Cookie notice

- [ ] Brief footer notice: "WOO Buddy gebruikt alleen functionele cookies. Meer informatie."
- [ ] Links to cookie policy page

## Acceptance Criteria

- All four legal pages accessible and rendered
- Landing page has complete meta tags
- Social sharing shows proper preview card
- Favicon displays in browser tabs

## Notes

- Have a lawyer review legal pages before public launch
- Cookie consent banner is NOT required (only essential session cookies, no tracking)
