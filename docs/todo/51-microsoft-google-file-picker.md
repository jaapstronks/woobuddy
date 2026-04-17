# 51 — Microsoft 365 / Google Drive file picker (client-side)

- **Priority:** P1
- **Size:** M (1–3 days per provider, L total)
- **Source:** Competitor landscape 2026-04 — Redactable/Tonic lead on this; #1 enterprise friction fix
- **Depends on:** Nothing functionally; coordinate copy with #44 and #40
- **Blocks:** Nothing — unlocks enterprise conversations

## Why

Nearly every Dutch government reviewer's source documents live in **SharePoint, OneDrive, or (increasingly) Google Workspace**, not on their desktop. Today WOO Buddy only accepts drag-and-drop from the local filesystem, which forces the reviewer to download the file from M365 first, then upload it to us. That extra "save to Downloads" step is both friction *and* a privacy regression (the file touches the local disk in a location the reviewer may forget to clean up).

Redactable, Tonic, and PII Tools all lead their enterprise demos with "pick directly from SharePoint." Matching that capability is near-certainly the single highest-ROI feature for unlocking enterprise conversations — and crucially, **we can implement it without compromising the client-first architecture**.

Both Microsoft's [Graph File Picker v8](https://learn.microsoft.com/en-us/onedrive/developer/controls/file-pickers/) and Google's [Picker API](https://developers.google.com/drive/picker) run entirely in the user's browser. The picker UI is hosted by the provider, returns a file reference to our JS code, and we download the bytes directly in the browser via the provider's OAuth-scoped download URL. **The file never traverses our server.** We get to keep the one-sentence trust claim intact.

This is also a Team-tier marketing asset: "Haal uw document rechtstreeks uit SharePoint — zonder download-upload-omweg, zonder dat het onze servers ooit raakt" is a sentence that sells itself to gemeente-IT.

## Scope

### Frontend

- [ ] **New `$lib/services/file-picker/` module** with a provider-agnostic interface:
  - `pickFromMicrosoft(): Promise<File>` — launches Graph File Picker in popup/iframe, user authenticates with their work/school account, picks a file, we receive a download URL + auth token, fetch the bytes in the browser, return a `File`
  - `pickFromGoogle(): Promise<File>` — launches Google Picker, same shape
  - Each provider registered behind a feature flag so we can ship Microsoft first (priority) and Google later
- [ ] **Upload area redesign** (`FileUpload.svelte`): three entry points side by side
  - "Sleep hierheen of klik om te kiezen" (existing local upload)
  - "Uit SharePoint / OneDrive" with Microsoft logo
  - "Uit Google Drive" with Google logo
  - Provider buttons are `sl-button` with provider icon; responsive wrap to vertical stack on mobile
- [ ] **Auth flow**: use MSAL.js for Microsoft and gapi/GIS for Google. Scopes are minimal read-only file scopes (`Files.Read` / `drive.file` for opened files only). No app registration asking for Sites.Read.All or similar — scope strictly to what the picker needs.
- [ ] **Post-pick UX**: show "Uw bestand wordt direct uit [SharePoint/Drive] naar uw browser gehaald. Het passeert onze servers niet." as a copy treat during the transfer progress bar. This is the trust moment.
- [ ] **Graceful degradation**: if the tenant has blocked third-party app consent (common in stricter gemeenten), catch the consent error and show a copy block explaining "Uw organisatie staat externe apps nog niet toe. Vraag uw beheerder om WOO Buddy toe te voegen, of download het bestand voor nu handmatig." with a link to self-host.
- [ ] **Support for converted formats** via #46: if the picked file is a `.docx` in SharePoint, it runs through the client-side conversion pipeline just like a local `.docx` would. Picker is purely an ingestion source.

### App registrations

- [ ] **Azure AD / Entra ID app registration** for WOO Buddy (hosted tier only):
  - Multi-tenant, redirect URIs for prod + staging
  - Minimal delegated scopes (`Files.Read` + `User.Read`)
  - Document the admin-consent URL so a gemeente IT admin can one-click approve for their tenant
- [ ] **Google Cloud project** with Picker API + Drive API enabled, OAuth consent screen configured, verified
- [ ] **Self-hosters get their own registrations**: add a config section in `docs/self-hosting/` explaining how to create their own Azure AD app and Google project and drop the client IDs into env vars. We don't share our production app IDs with self-host deployments.

### Backend

**Nothing.** No server-side OAuth callback, no token proxying, no server-side download. If this todo requires a backend change, the design is wrong.

### Privacy / trust copy

- [ ] Update landing-page trust section (`Hero.svelte`) to add: *"Kies direct uit SharePoint, OneDrive of Google Drive — uw document gaat rechtstreeks naar uw browser, zonder tussenstop bij ons."*
- [ ] Update `/try` page to show the trust claim next to the picker buttons
- [ ] Update `docs/trust/` or equivalent public page (coordinate with #40 legal/SEO) to explain the OAuth scopes we request and why
- [ ] Network-isolation test: assert that picking a file from Microsoft or Google results in **zero** outbound requests to the WOO Buddy server during the pick + download phase

### Analytics

- [ ] Plausible events (#41): `picker.launched` + `picker.completed` + `picker.cancelled` with `{provider}` property. No file metadata, no tenant IDs.

## Acceptance

- User on `/try` sees three upload entry points: local, Microsoft, Google
- Clicking "Uit SharePoint / OneDrive" opens the Microsoft picker in a popup, user authenticates with their work account, selects a PDF, and lands in `/review/[docId]` with the document loaded — **with zero network traffic to WOO Buddy's server during the pick+download phase** (verified by test)
- Same for Google Drive
- Tenants that have blocked third-party apps see a graceful "vraag uw beheerder" screen, not a cryptic OAuth error
- Self-host docs include step-by-step instructions for creating the two OAuth apps
- Copy on landing + `/try` explicitly names the direct-to-browser path as a trust feature

## Not in scope

- SharePoint site-level enumeration (full folder tree browser inside WOO Buddy) — the Microsoft-hosted picker handles this
- Writing back to SharePoint / Drive on export — one-way read-only for V1; "save redacted back to source" is a natural V2 but introduces write scopes that raise admin-consent hurdles. Keep V1 minimal.
- Dropbox, Box, iCloud — add later if a pilot asks. Microsoft is 90% of the value for our market.
- Zaaksysteem picker (Djuma/Decos/Corsa) — belongs to #59

## Open questions

- Do we want a "recently picked" client-side history (IndexedDB of file names + provider) to speed up repeat reviews? Nice-to-have; out of V1.
- MSAL popup vs redirect flow — popup is better UX on desktop but some IT policies block popups. Start with popup, fall back to redirect if `window.open` returns null.
