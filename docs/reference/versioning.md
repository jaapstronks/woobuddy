# Versioning & releases

How WOO Buddy version numbers work, what counts as a breaking change, and how a
release gets cut. The automation is [`release-please`](https://github.com/googleapis/release-please);
this document is the human-readable contract around it.

## The version number

WOO Buddy follows [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`
(e.g. `0.2.0`). The three parts are independent counters, not decimals — `0.9.0`
is followed by `0.10.0`, not `1.0`.

| Part      | Bumped when …                                       | Signal to someone running WOO Buddy                                            |
| --------- | --------------------------------------------------- | ------------------------------------------------------------------------------ |
| **MAJOR** | a backward-incompatible change ships                | Read the notes before upgrading; you may need to adjust config or an API call. |
| **MINOR** | a backward-compatible feature ships (resets PATCH)  | Safe to upgrade; nothing you had breaks, and there's something new.            |
| **PATCH** | a backward-compatible fix ships                     | Blindly safe; often you want it (bug/security).                                |

There is exactly **one version number for the whole repository**. `VERSION` in the
root is the source of truth; `frontend/package.json`, `frontend/package-lock.json`
and `backend/pyproject.toml` are bumped from it by the same automation, so there is
no hand-maintained copy that can drift.

### Before 1.0: no MAJOR bumps

WOO Buddy is pre-1.0 and stays there until the tool has been through a real Woo
procedure at more than one organization. In that phase a MAJOR bump communicates
the wrong thing — `1.0.0` reads as "this is finished and supported", which is a
promise we are not yet in a position to make.

So until that moment, **the version stays in `0.x`**: a feature is a MINOR bump
(`0.2.0` → `0.3.0`) and a fix is a PATCH (`0.3.0` → `0.3.1`). Breaking changes are
still _documented_ — the `⚠ BREAKING CHANGES` section in the changelog is the
point — but they ship as a MINOR bump.

Keep writing the `BREAKING CHANGE:` trailer when a change genuinely meets the
criteria below; the warning in the notes is worth more than the digit. What keeps
it from becoming a MAJOR is `bump-minor-pre-major: true` in
`release-please-config.json`: while the version is below 1.0, a breaking change
bumps MINOR, and so does a `feat:` (`bump-patch-for-minor-pre-major: false`). A
`0.x` release carrying a `⚠ BREAKING CHANGES` section is therefore the intended
shape here, not a mistake. Still read the Release PR's version before merging:
if it ever proposes something else, the config has drifted, so fix that and
override the number (see [Correcting a version](#correcting-a-version)).

`1.0.0` is reserved for a deliberate moment, and it is the moment the stable
surfaces below become promises rather than descriptions.

## Merges are not releases

Merging to `main` is **continuous integration** — internal, and it may happen
several times a day. A **release** is an **outward signal** to people running
WOO Buddy that a moment is worth updating to. The two are deliberately decoupled:
merges flow continuously, releases are cut when enough has accumulated to be
worth someone's attention. Cutting a release on every merge would destroy the
signal value of the number.

## What counts as a breaking change

"Breaking" means nothing until the stable surface is named. For WOO Buddy, a
change is breaking only if it breaks one of these for an existing install:

1. **The HTTP API under `/api`** — removing or reshaping a route, a request field
   or a response field. `/api/analyze`, `/api/export/redact-stream` and
   `/api/health` are the ones a self-hoster or an integration can actually see.
2. **The export contract** — the shape of what leaves the tool: the redacted PDF
   itself, the accompanying substantiation report (`onderbouwingsrapport`), and
   the metadata written into them (`/Lang`, XMP, per-redaction annotations).
   Someone's Woo publication workflow reads those artifacts.
3. **Configuration** — `.env` keys and the `docker-compose*.yml` setup that
   self-hosters run. A new required variable with no default, or a renamed key,
   breaks a running install on upgrade.
4. **The client-side session state** — the IndexedDB schema in
   `frontend/src/lib/services/idb.ts` (`DB_VERSION`, the `documents`,
   `extractions` and `session-state` stores). A reviewer's in-progress work lives
   there, in their browser; an upgrade that cannot read it loses their work. The
   upgrade handler is keyed to `event.oldVersion` precisely so this does not
   happen — a change that drops persisted state without a migration is breaking.

Everything else — internal modules, Dutch UI microcopy, detection tuning, most
refactors — is MINOR or PATCH. When in doubt: if a self-hoster or a reviewer has
to change or redo something on upgrade, treat it as breaking.

Two things this list deliberately does _not_ make breaking:

- **Detection getting better or worse at a specific pattern.** More or fewer
  suggestions is the product changing, not a contract breaking; the reviewer
  confirms every Tier 2 suggestion anyway. Recall and false-positive shifts belong
  in the release notes as a `feat`/`fix`, not as a breaking change.
- **Moving or splitting an internal module.** WOO Buddy publishes no JS or Python
  package surface; `frontend/src/lib/` and `backend/app/` internals are not a
  contract. A fork that patched a specific file has to reconcile, and that is what
  forking costs.

### Wire changes are never titled `refactor:`

The changelog is generated from commit titles, and `refactor:` commits are
dropped from it. So the title is not a description of the diff — it is a routing
decision about whether the change reaches the changelog and the version number.

**A commit that changes any of the four surfaces above is titled `feat:` or
`fix:`** (with a `!` or a `BREAKING CHANGE:` footer when breaking), even when the
diff is internally refactor-shaped. `refactor:` is reserved for changes with no
observable effect on any of them.

## Commit conventions

Releases are computed from [Conventional Commits](https://www.conventionalcommits.org/).
Because `main` only accepts squash-merges, the **PR title** is what release-please
reads — keep it a valid Conventional Commit. A scope is optional:
`feat(review): …`.

| Prefix                                                                       | Bump  | Changelog section       |
| ---------------------------------------------------------------------------- | ----- | ----------------------- |
| `feat:`                                                                      | MINOR | Added                   |
| `fix:`                                                                       | PATCH | Fixed                   |
| `security:`                                                                  | PATCH | Security                |
| `perf:` / `revert:`                                                          | PATCH | Changed                 |
| `docs:` `chore:` `refactor:` `style:` `test:` `ci:` `build:`                 | none  | hidden                  |
| any of the above with **`!`** (e.g. `feat!:`) or a `BREAKING CHANGE:` trailer | MAJOR (MINOR pre-1.0) | flagged breaking |

Only `feat`/`fix`/`security`/`perf`/`revert` and breaking changes surface in the
changelog and move the version; the rest are invisible to consumers by design.
That is why the repository's Dependabot traffic — dozens of `chore(deps)` commits
— never shows up in a release note.

## How a release is cut

1. Feature PRs are merged to `main` as usual, with Conventional-Commit titles.
2. On every push to `main`, the `release-please` workflow maintains **one open
   Release PR** titled `chore(main): release X.Y.Z`. It carries the computed next
   version and a generated `CHANGELOG.md` entry, and it grows as more merges land.
3. When enough has accumulated to be worth shipping, you **merge the Release PR**.
   That single merge bumps `VERSION`, `frontend/package.json`,
   `frontend/package-lock.json` and `backend/pyproject.toml`, finalizes the
   changelog, tags `vX.Y.Z` and publishes a **GitHub Release**. You never pick the
   number by hand — it is derived from what is in the PR.
4. The tag triggers `.github/workflows/release.yml`, which builds and pushes the
   multi-arch images `ghcr.io/jaapstronks/woobuddy-api:vX.Y.Z` and
   `-frontend:vX.Y.Z` (plus `:latest` for stable tags).
5. Deploy from the tag, not from an arbitrary commit on `main`.

### Two changelogs, on purpose

- **`CHANGELOG.md` in the repository** is generated, English, and at
  commit granularity. It is for developers and self-hosters, who want to know
  exactly what moved.
- **`/changelog` on woobuddy.nl** is hand-written, Dutch, and at
  reader-benefit granularity. It is for the civil servant doing the redacting,
  who wants to know what is different about their afternoon. The notes live in
  `frontend/src/content/releases/`; `_template.md` is the shape.

The Dutch note for a version is written and merged to `main` **before** the
Release PR for that version is merged, so that the release and the note land
together.

### Release ritual

Cutting a release is a deliberate step, not a by-product. It belongs to a
review-and-merge session, and it is done in this order:

1. The Dutch release note for the upcoming version is already on `main`, with
   `latest: true` moved to it in that same commit.
2. Read the Release PR: the version is right for what is in it, and the generated
   changelog is not surprising.
3. Merge it. Wait for `release.yml` to finish pushing the images.
4. Deploy from the tag and verify: the GitHub Release is the latest, `/changelog`
   shows the note, the footer and `/api/health` report the new version.

Cadence: cut a release when something has landed that a municipality or a
self-hoster would notice, and in any case not more than a month apart while
there are unreleased `feat`/`fix` commits on `main`.

## Correcting a version

Step 3 above says you never pick the number by hand, and that holds for the normal
path. The exception is when a commit already on `main` computed the wrong bump — a
`BREAKING CHANGE:` trailer on something that is not breaking, or a `feat:` that
was really a `fix:`. History cannot be unwritten, so you override the result instead.

Push a commit to `main` whose message carries a `Release-As:` trailer with the
version you actually want:

```
docs: describe the export contract more precisely

Release-As: 0.4.0
```

On the next push, release-please rewrites the open Release PR to that version:
title, `VERSION`, tag and changelog heading. The generated changelog _body_ still
reflects the commits (a `⚠ BREAKING CHANGES` section stays), which is correct: the
note was accurate, only the digit was wrong.

Use this sparingly. Every use means the commit convention failed upstream, so fix
that too.

## Where the version shows up

- **`VERSION`** in the repository root — the source of truth.
- **`/api/health`** returns `"version"`, read from the installed package metadata.
  In a development virtualenv without an editable install it reports `"dev"`.
- **The site footer** shows `v0.x.y`, compiled in from `package.json` at build
  time.
- **`deploy/deploy.sh`** prints the deployed `git describe --tags` and the version
  that the live `/api/health` reports, so "production is on `450ccd1`" becomes
  "production is on v0.2.0".

## One-time setup

- **`RELEASE_PLEASE_TOKEN` secret (required in practice).** Pull requests and tags
  created by the built-in `GITHUB_TOKEN` do not trigger other workflows. Without a
  PAT that means two things go wrong: the Release PR never runs CI, so the required
  checks on `main` can never pass, and the tag it eventually pushes never triggers
  `release.yml`, so no images are built. Add a **fine-grained PAT** (repository
  access: this repository only; permissions: **Contents: Read and write**,
  **Pull requests: Read and write**) as a repository secret named
  `RELEASE_PLEASE_TOKEN`. The workflow falls back to `GITHUB_TOKEN` when it is
  missing, but in this repository that run fails: GitHub Actions is not allowed to
  create pull requests here (Settings → Actions → General → Workflow permissions),
  so a red `release-please` run on `main` means the secret is missing, not that
  the configuration broke.

## How people hear about a release

- **GitHub Releases + "Watch → Custom → Releases"** — a watcher is mailed on each
  release and only on releases, which is the best reason to keep them scarce.
- **The releases feed:** `https://github.com/jaapstronks/woobuddy/releases.atom`.
- **`/changelog` on woobuddy.nl** — the Dutch, reader-facing version.
- **Self-hosters pin tags, not `main`** (see `deploy/README.md` → "Upgrading
  between releases"), so a new tag is itself how they learn there is something to
  pull.
