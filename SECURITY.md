# Security Policy

Thanks for helping keep WOO Buddy safe. Because WOO Buddy is used to redact privacy-sensitive Dutch government documents, we take security reports seriously and prioritize them over feature work.

## Supported versions

Only the `main` branch and the latest deployed release of <https://woobuddy.nl> receive security fixes. There is no LTS branch. Self-hosters are expected to track `main`.

## Reporting a vulnerability

**Please do not open a public GitHub issue for security problems.**

Report privately through either channel:

1. **GitHub Private Vulnerability Reporting** — preferred. Use the "Report a vulnerability" button under the [Security tab](https://github.com/jaapstronks/woobuddy/security) of this repository. This creates a private advisory that only maintainers can see.
2. **Email** — `jaapstronks@gmail.com`. Use the subject line `[WOO Buddy security]`. PGP is not required, but encrypted reports are welcome if you have a preferred key exchange.

Please include:

- The affected component (frontend, backend, deploy config) and version/commit hash
- Reproduction steps or a proof of concept
- The impact you believe the issue has (data exposure, privilege escalation, denial of service, etc.)
- Any suggested remediation, if you have one

### What to expect

- We aim to acknowledge reports within **3 business days** (this is a small project — please be patient).
- We will confirm whether the report is a valid vulnerability and share a rough timeline for a fix.
- Credit in the release notes is offered by default. Tell us the name or handle to use, or say you'd prefer to stay anonymous.
- We do **not** operate a paid bug bounty program.

## Scope

In scope:

- `jaapstronks/woobuddy` source code (frontend, backend, deploy scripts)
- <https://woobuddy.nl> and its subdomains when exercised against documents and accounts you control

Out of scope:

- Self-hosted instances you do not operate (report to that operator)
- Third-party dependencies (report upstream, then optionally CC us)
- Findings that require physical access to a user's machine or social-engineering of a user
- Volumetric load issues against the rate limiter itself (`/api/analyze` is rate-limited; report logic bypasses, not the limit itself)

## Coordinated disclosure

We prefer **coordinated disclosure**: give us a reasonable window (typically 30–90 days depending on severity) to patch before going public. We will keep you updated on progress and coordinate a disclosure date with you.

If a fix requires a self-host upgrade, we will publish the advisory only after a fixed release is tagged, so operators have a clear upgrade path.

## Hall of fame

Thanks to the security researchers who have helped improve WOO Buddy. _List is empty so far — be the first._
