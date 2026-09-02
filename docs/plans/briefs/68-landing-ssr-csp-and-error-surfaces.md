# 68 — Landing page ships Shoelace, CSP gaps, raw errors in the lead form

> Status: aanzet · 2026-09-02 · TODO #68 · hangt samen met: —

- **Priority:** P1 (doctrine violation + two user-visible failures)
- **Size:** S–M
- **Source:** tighten-scan 2026-09-02

> Line numbers verified on `origin/main` @ `83fecbb`; re-verify before editing.
> Second pass (review of PR #99, 2026-09-02): all claims hold; two pointers
> corrected (4, 5) and finding 5 reworded.

## Findings

1. **Shoelace *is* on the SSR landing page — confirmed.**
   `lib/components/shared/ProgressSteps.svelte:26` and
   `shared/ProviderPickerButtons.svelte:16` import
   `progress-bar/progress-bar.js` at top level. Chain: `routes/+page.svelte`
   → `landing/Hero.svelte` → `landing/HeroUploadPanel.svelte:5-6,263,351` →
   `shared/FileUpload.svelte:3,142`. There is no `routes/+layout.ts` or
   `+page.ts` with `ssr = false`, so Lit is evaluated in Node on every `/`
   render and shipped in the landing chunk. Three comments claim the opposite
   (`landing/OcrOptInDialog.svelte:10`, `marketing/LeadCaptureForm.svelte:15`,
   `routes/review/+layout.ts:2`). Fix: a plain `<div>` + CSS bar in both.
   Nuance: importing `progress-bar.js` in Node does not throw, so this is a
   bundle-size, eval-cost and doctrine problem, not a live SSR 500.
2. **Raw JSON shown as Dutch copy in the lead form.** `lib/api/client.ts:48-50`
   sets `ApiError.message = await res.text()` (a FastAPI `{"detail": ...}` body);
   `marketing/LeadCaptureForm.svelte:56-59` renders it verbatim. After the
   Listmonk migration every failure (500/502/503) shows a JSON blob.
   `upload-flow.ts:74-81` `describeError` has the same flaw. Parse `detail`.
3. **CSP blocks consumer-OneDrive downloads — plausible.** `svelte.config.js:78-100`
   allows `*.sharepoint.com` / `*.onedrive.com`; personal accounts'
   `@microsoft.graph.downloadUrl` resolves to `*.files.1drv.com` /
   `*.storage.live.com`. `file-picker/microsoft.ts:417` then fails as
   `PickerError('network')`. Verify with a personal account, then add the hosts.
4. **Microsoft picker robustness** (`file-picker/microsoft.ts`): `:212-223`
   `popup.document.body` used synchronously after `window.open('')`;
   `:259-268` `settle()` never clears the 5-minute timeout (`:384`) or the
   500 ms poll (`:394`; the poll callback itself does clear both, so the fix
   belongs in `settle()`); `:148-154` a failed `acquireTokenPopup` escapes as a
   bare `Error` instead of `PickerError('popup-blocked'|'cancelled')`.
5. **Picker files get an extension-only PDF check.** `google.ts:225` /
   `microsoft.ts:487` default `type` to `application/pdf`; the files do pass
   through `validate()` (`FileUpload.svelte:92` → `:37`), but that checks only
   the `.pdf` extension, so the fabricated MIME type is never tested. `FileUpload.svelte:51-57` never calls `onfiles` when all
   files are invalid, so stale `pendingDocId`/`steps` survive in
   `HeroUploadPanel`.
6. **Analytics bypass.** `file-picker/analytics.ts:23-28` writes to
   `window.plausible` directly and fires three events (`picker.*`) that are
   absent from `analytics/events.ts:45-71`, whose header says "if an event
   isn't here, it isn't fired". Delete the file, add the events, use `track()`.
7. **CSP fossils and `{@html}`.** `svelte.config.js:60-61` allows Google Fonts
   while `app.css:8-9` says "system fonts only". `routes/+page.svelte:24-63`
   injects JSON-LD via `{@html}` (literal today, but the only `{@html}` outside
   review). `hooks.server.ts:56-61` attaches the proxy secret to any URL
   containing `/api/`, not to the backend origin.
8. **`routes/+error.svelte:5-8`** is monospace, English, leaks
   `page.error.message`, no landmark.
9. Related, already tracked: #63 (release image bakes `localhost:8000`;
   `.github/workflows/release.yml` passes no build-arg).

## Gate

- A vitest that imports `routes/+page.svelte`'s dependency graph and asserts no
  `@shoelace-style` module is reachable (same idea as
  `file-picker/network-isolation.test.ts`).
- `analytics/events.ts` stays the single event registry; grep-test that no
  file other than `plausible.ts` touches `window.plausible`.

## Acceptance criteria

- [ ] `/` renders with zero Shoelace modules in the SSR bundle.
- [ ] Lead-form errors show Dutch copy for 500/502/503.
- [ ] Consumer OneDrive pick completes on production CSP.
