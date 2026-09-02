# 72 — Lead form returns 500 on woobuddy.nl: no mail config reaches the api container

> Status: uitvoeringsklaar · 2026-09-02 · TODO #72 · hangt samen met: `feat/brevo-to-listmonk` (lokale branch, c1ee83d), #38

- **Priority:** P0 (the only conversion path on the landing page is dead; every submitter sees "Verzenden is tijdelijk niet beschikbaar")
- **Size:** S (code) + secrets on the VPS (Jaap or a session with `op` access)
- **Source:** production probe during the review of PR #99, 2026-09-02

## What was measured

- `POST https://woobuddy.nl/api/leads` with a valid payload → **HTTP 500** in 0.15 s,
  body `{"detail":"Verzenden is tijdelijk niet beschikbaar."}`; an empty body → 422, so
  the route itself is live.
- Server log (`docker compose -f docker-compose.prod.yml logs api`):
  `{"event": "leads.brevo_api_key_missing", "level": "error", …}` on the same request id.
- Inside the running `api` container every `BREVO_*` variable has length 0.
  `/opt/woobuddy/.env` contains only `DBASE_PASSWORD`.
- `docker-compose.prod.yml` § `api` passes a single `environment:` entry (`DATABASE_URL`)
  and has no `env_file:`; `deploy/deploy.sh` writes only the DB password into `.env`.

Conclusion: the lead form has never had mail credentials in production. This is not a
Brevo outage or an expired key: the configuration never reached the container.

## Fix (one PR + one deploy)

1. **Land the Listmonk migration.** Push `feat/brevo-to-listmonk` (rebase on `main`,
   20+ commits behind) after the three scan points: (a) prod compose passes the mail
   config, (b) CR/LF filter on `name`/`organization` before they go into mail headers,
   (c) delete the Brevo narration in `leads.py`. Brevo is being cancelled, so do not
   revive the `BREVO_*` path.
2. **Prod compose**: add `env_file: .env` to the `api` service (or list
   `SCALEWAY_SECRET_KEY`, `SCALEWAY_PROJECT_ID`, `SCALEWAY_TEM_REGION`, `TEM_FROM_EMAIL`,
   `TEM_FROM_NAME`, `NOTIFICATION_EMAIL`, `LISTMONK_URL`, `LISTMONK_LIST_UUID` explicitly
   under `environment:`). `deploy/deploy.sh` must write those keys into
   `/opt/woobuddy/.env` alongside `DBASE_PASSWORD`; document the source (1Password item)
   in `deploy/README.md`.
3. **Fail loud, not quiet**: log a startup warning when `scaleway_secret_key` is empty
   in a non-dev environment, and add a `/api/health` field or a smoke check in
   `deploy/install.sh` so a missing key is caught at deploy time, not by a visitor.
4. **Deploy and verify**: one real submission from the live form (or `curl`) returns
   200 and the notification mail lands in `NOTIFICATION_EMAIL`. Then remove the test
   subscriber if `newsletter_opt_in` was used.

## Scaleway set-up via the CLI (the session can do this)

Jaap's direction (2026-09-02): transactional mail moves to Scaleway TEM, which he already
uses; set it up through `scw`, not the console. State found on the Mac:

- `scw` 2.53 is installed. Profile `bolster` (Bureau Bolster, the legal operator of
  woobuddy.nl) owns project `4304a571-309f-4113-91a2-13f55f5e8bf2` with TEM domains
  `mail.dreamkit.eu`, `dreamkit.eu`, `republiek.org`, `controlealtdelete.nl`, all `checked`.
  The default profile (org "Charlie") has no TEM domains: use `scw -p bolster`.
- Steps: (1) `scw -p bolster iam application create name=woobuddy-leads` + a policy with
  `TransactionalEmailFullAccess` on that project + `scw iam api-key create
  application-id=…` → `SCALEWAY_SECRET_KEY`/`SCALEWAY_PROJECT_ID`. Store the key in
  1Password (vault Bolster), never in the repo. (2) Sender: start with the already
  verified `noreply@mail.dreamkit.eu` (the branch default) so the fix ships today;
  optionally `scw -p bolster tem domain create domain-name=woobuddy.nl` and add the
  SPF/DKIM/MX records it returns at TransIP, then `tem domain check`, and switch
  `TEM_FROM_EMAIL` to `noreply@woobuddy.nl`. (3) `LISTMONK_LIST_UUID`: the "WOO Buddy -
  leads" list on `listmonk.dreamkit.eu` (see the Listmonk admin; wings-monorepo briefing
  2026-06-04 names it).

## Jaap beslist

- `NOTIFICATION_EMAIL` (where lead mails land) and whether the sender moves to
  `woobuddy.nl` now or later.

## Gate

- `deploy/install.sh` (or the health check) fails the deploy when the mail config is
  missing, so this class of misconfiguration cannot ship silently again.

## Acceptance criteria

- [ ] `POST /api/leads` on woobuddy.nl returns 200 for a valid payload.
- [ ] The notification mail arrives; the newsletter opt-in lands in the Listmonk list.
- [ ] A deploy without the mail secrets fails visibly.
