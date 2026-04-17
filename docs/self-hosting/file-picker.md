# Configuring the SharePoint / OneDrive / Google Drive picker

WOO Buddy can ingest a PDF directly from a reviewer's Microsoft 365
(SharePoint, OneDrive) or Google Drive — no download-upload detour,
and the file **never touches the WOO Buddy server**. The picker UI is
hosted by the provider, OAuth happens in the reviewer's own browser,
and the PDF bytes stream from the provider's CDN straight into the
browser tab.

This page explains how to wire up the two OAuth apps a deployment
needs to enable the buttons. If you don't want the buttons, leave the
env vars blank and the code path stays dark — the drag-and-drop
upload keeps working as before.

## TL;DR — environment variables

Set these in `frontend/.env` (or in your deployment's env file) before
building the frontend:

```bash
# Microsoft Graph File Picker v8 — Azure AD / Entra ID app
PUBLIC_MS_PICKER_CLIENT_ID=<application_client_id>
# Multi-tenant default: https://login.microsoftonline.com/common.
# Single-tenant deployments pin to their own tenant ID:
#   https://login.microsoftonline.com/<tenant-id>
PUBLIC_MS_PICKER_AUTHORITY=https://login.microsoftonline.com/common

# Google Picker API — Google Cloud project
PUBLIC_GOOGLE_PICKER_CLIENT_ID=<oauth_client_id>.apps.googleusercontent.com
PUBLIC_GOOGLE_PICKER_API_KEY=<api_key>
PUBLIC_GOOGLE_PICKER_APP_ID=<gcp_project_number>
```

A provider button only renders when **all** variables for that
provider are non-empty. Missing one means the reviewer doesn't see
the button — which is preferable to a button that fails at runtime.

## Microsoft 365 — Azure AD / Entra ID app registration

1. **Sign in to the Microsoft Entra admin center** at
   <https://entra.microsoft.com> with an account that can create app
   registrations for your tenant.
2. **Create a new app registration.**
   - Name: `WOO Buddy File Picker` (or similar; users will see this
     in the consent screen).
   - Supported account types: pick one.
     - **Multi-tenant + personal accounts** → hosted tier or any
       deployment that serves reviewers across gemeenten.
     - **Single tenant** → self-host deployments inside a single
       gemeente.
   - Redirect URI: `Single-page application (SPA)` with value
     `https://<your-domain>` (for prod) plus any staging/dev URLs
     you need. MSAL.js uses the page origin; no `/auth/callback`
     path is required.
3. **Under `API permissions`, add these delegated Graph scopes:**
   - `User.Read` — to read the signed-in user's profile (lets MSAL
     discover their OneDrive/SharePoint host).
   - `Files.Read` — to read files the user picks.
   - `Files.Read.All` — required by the v8 File Picker protocol
     for SharePoint documents the user has access to but doesn't
     own. *Despite the `.All` suffix this is still a delegated
     scope: it only grants what the signed-in user can already see.*
   - Do **not** add `Sites.Read.All` or any application-level scope.
     They would require admin consent for every tenant and are not
     needed for the picker.
4. **Copy the `Application (client) ID`** from the `Overview` tab
   and paste it into `PUBLIC_MS_PICKER_CLIENT_ID`.
5. **Optional: admin-consent URL.** Multi-tenant deployments can
   give their gemeente-IT contacts a one-click consent link of the
   form:
   ```
   https://login.microsoftonline.com/<tenant-id>/adminconsent?client_id=<application_client_id>
   ```
   Once the admin approves it, all users in that tenant sign in
   without individual consent prompts.

Stricter tenants block third-party app consent entirely. In that
case the picker raises a "consent" error and WOO Buddy shows a
reviewer-friendly message telling them to ask their IT admin or
download the file manually. That copy is in
`ProviderPickerButtons.svelte` if you want to tweak it.

## Google Drive — Google Cloud project

1. **Go to the Google Cloud console** at
   <https://console.cloud.google.com> and create or select a project
   for WOO Buddy.
2. **Enable APIs.** Under `APIs & Services > Library`, enable
   - `Google Picker API`
   - `Google Drive API`
3. **OAuth consent screen.**
   - User type: `External` (unless you're strictly inside a Google
     Workspace domain).
   - Scopes: `https://www.googleapis.com/auth/drive.file` — this
     is the **narrowest** scope Drive supports for the picker use
     case. It grants per-file access *only* to files the user
     explicitly opens through our picker; the rest of their drive
     stays invisible to the app.
   - Publishing status: move to `In production` and submit for
     verification before going live — unverified apps show a scary
     warning screen that civil servants will rightly abandon.
4. **Create OAuth 2.0 credentials.**
   - Application type: `Web application`.
   - Authorized JavaScript origins: `https://<your-domain>` and
     any dev/staging origins.
   - Authorized redirect URIs: leave blank. The GIS token flow
     doesn't use redirects for implicit-flow access-token requests.
   - Copy the Client ID into `PUBLIC_GOOGLE_PICKER_CLIENT_ID`.
5. **Create an API key** (`Credentials > Create credentials > API
   key`). Restrict it to:
   - HTTP referrers matching your domain(s).
   - API: `Google Picker API` only.
   Copy the key into `PUBLIC_GOOGLE_PICKER_API_KEY`.
6. **Project number**, visible on the `Dashboard`, goes into
   `PUBLIC_GOOGLE_PICKER_APP_ID`. (Google's Picker SDK calls this
   `appId`, confusingly — it's the numeric project identifier, not
   the OAuth client ID.)

## Self-hosters: do NOT share our production app IDs

The hosted `woobuddy.nl` deployment registers its own OAuth apps
and keeps those client IDs out of this repo. If you run WOO Buddy
on your own infrastructure, **create your own app registrations**
using the steps above. Reasons:

- Your reviewers should authenticate against an app registered by
  *you*, not us. The consent screen names the app — a reviewer
  from gemeente Arnhem should see "Gemeente Arnhem WOO Buddy",
  not our domain.
- OAuth rate limits and audit trails belong to whoever owns the
  registration.
- Revocation, tenant restrictions, and admin consent should be
  under the deploying organization's control.

## Verifying "the file never touches our server"

This is the trust-critical guarantee. Two layers of defence:

1. **Source scan.** `src/lib/services/file-picker/` does not import
   `$lib/api/client` or `PUBLIC_API_URL`. A CI test
   (`network-isolation.test.ts`) asserts this.
2. **Runtime fetch assertion.** The same test exercises the Google
   download helper with a mocked `fetch` and verifies every URL
   stays on `googleapis.com`. If a future change accidentally
   routes a picker byte through the WOO Buddy backend, that test
   fails.

If you're auditing a deployment yourself, open DevTools' Network
tab on `/try`, pick a file from SharePoint or Drive, and confirm:

- The OAuth token flow talks to `login.microsoftonline.com` /
  `accounts.google.com` only.
- The actual file bytes come from
  `*-my.sharepoint.com` / `*.sharepoint.com` / `graph.microsoft.com`
  (Microsoft) or `www.googleapis.com` (Google).
- No request hits your WOO Buddy origin during the pick-and-download
  phase. The only WOO Buddy request you should see is the subsequent
  `POST /api/analyze` with the extracted text layer — same as for a
  drag-and-drop upload, and without any PDF bytes.
