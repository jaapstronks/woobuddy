# 40 — Legal Pages & SEO

- **Priority:** P2
- **Size:** S (< 1 day)
- **Source:** Testing & Polish briefing, Sections 10 (SEO) + (Legal pages)
- **Depends on:** Nothing
- **Blocks:** Nothing (but required before public launch)

## Why

A Dutch SaaS product processing government documents needs legal pages. Government organizations will want a data processing agreement before uploading real documents. SEO ensures the tool is discoverable.

## Scope

### Legal pages

- [x] `/privacy` — Privacyverklaring (what data, how processed, retention, access). Emphasizes client-first: PDFs never leave the browser, no document content stored, text analysis ephemeral.
- [x] `/terms` — Algemene voorwaarden (usage terms, liability, open-source license, Dutch law).
- [x] `/cookies` — Cookie policy (minimal: session cookies only, no tracking; explicit about Plausible being cookieless).
- [x] `/verwerkersovereenkomst` — DPA model text scoped to account data + detection metadata only (no document content).
- [x] All pages in Dutch (SSR-compatible Svelte route group, shared `+layout.svelte` with prose styling).
- [x] Footer links to all legal pages.

### SEO meta tags (landing page)

- [x] `<title>` — set on landing page (`+page.svelte`) and as default in `app.html`.
- [x] `<meta name="description">` — Dutch description on landing + default in `app.html`.
- [x] Open Graph tags: `og:title`, `og:description`, `og:image`, `og:url`, `og:type`, `og:locale`, `og:site_name`.
- [x] Twitter card: `summary_large_image` with `twitter:image` and alt text.
- [x] `og-image.png` (1200x630) present in `static/`, generated via `og-image.gen.py`.

### Favicon

- [x] Favicon set already present in `static/favicon/` (16x16, 32x32, 96x96, 192x192, apple-touch-icon 180x180, MS tiles, `manifest.json`).
- [x] Wired up in `app.html`.

### Cookie notice

- [x] Footer notice: "WOO Buddy gebruikt alleen functionele cookies. Meer informatie."
- [x] Links to `/cookies`.

## Acceptance Criteria

- [x] All four legal pages accessible and rendered.
- [x] Landing page has complete meta tags.
- [x] Social sharing shows proper preview card (og-image + twitter card in place).
- [x] Favicon displays in browser tabs.

## Notes

- Have a lawyer review legal pages before public launch. Placeholder contact addresses (`privacy@`, `dpa@`, `hallo@woobuddy.nl`) need to be set up or replaced.
- Cookie consent banner is NOT required (only essential session cookies, no tracking).

## Implementation (2026-04-16)

- Route group `frontend/src/routes/(legal)/` with shared `+layout.svelte` — Header + scoped prose styles + Footer, SSR on, no Shoelace. Keeps the four pages cheap to crawl and easy to share.
- Meta tags per page: `<title>`, `<meta name="description">`, `<link rel="canonical">`, `og:url`, `og:title`, `og:type=article`.
- Footer rebuilt into a grid of legal + project links; added a dedicated cookie line above the nav.
- `static/sitemap.xml` extended with the four legal URLs.
- Everything SEO/favicon-related on the landing page was already in place from earlier work — verified, untouched.
