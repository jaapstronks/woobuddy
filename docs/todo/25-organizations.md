# 06 — Organizations & Data Scoping

- **Priority:** P0
- **Size:** L (3–7 days)
- **Source:** Auth & Billing briefing, "Organizations" + "Revised Data Model" sections
- **Depends on:** #24 (Authentication)
- **Blocks:** #26, #27, #28

## Why

Without organizations, there's no ownership boundary. Dossiers float in a shared space. Every database query that touches user data must be scoped to an organization — this is the single most important security invariant for a multi-tenant SaaS.

## Assessment of Briefing Recommendation

The organization model is well-designed. Better Auth's organization plugin handles the hard parts (org CRUD, membership, active org on session). The key work is retrofitting `organization_id` onto every existing table and ensuring every query filters by it.

**Adopt as-is.** Two modifications:
1. Defer multi-organization switching to P3 — for MVP, a user belongs to one org.
2. Under client-first architecture (#00), organization scoping applies to **metadata only** (detection positions, articles, decisions, page reviews) — never to document content, which lives exclusively in the browser.

## Scope

### Better Auth organization plugin

- [ ] Enable organization plugin in Better Auth config
- [ ] Run migrations for organization, member, invitation tables
- [ ] Organization creation on first signup (prompt for team/municipality name)

### Database migration — add organization_id + client-first schema changes

- [ ] `dossiers` — add `organization_id` FK, add `created_by` FK to user
- [ ] `documents` — add `uploaded_by` FK to user. **Remove `minio_key_original` and `minio_key_redacted`** — PDFs are no longer stored server-side. Keep: `filename`, `page_count`, `status`, `organization_id`.
- [ ] `detections` — change `reviewed_by` from text to FK to user. **Remove `entity_text` column** (or make nullable and never populate) — sensitive text must not be stored on the server. Keep: `bounding_boxes`, `entity_type`, `tier`, `woo_article`, `review_status`, `confidence`.
- [ ] `audit_log` — change `actor` from text to FK to user, add `organization_id`. **Ensure `details` JSONB never contains entity text** — store action type + detection ID only.
- [ ] `public_officials` — verify already has org scope, add if missing
- [ ] `draft_comments` (when created) — use FK to user, not text
- [ ] `exports` (when created) — add `created_by` FK to user. Exports are now ephemeral (streamed, not stored in MinIO) — this table tracks export metadata/snapshots only.
- [ ] `page_reviews` (when created) — add `reviewer_id` FK to user
- [ ] `motivation_texts` — store generic article-based templates only, not entity-specific text. Entity-specific motivation is composed client-side for display.

### Query scoping

- [ ] Every repository/service method that queries dossiers, documents, or detections must include `WHERE organization_id = :org_id`
- [ ] FastAPI middleware extracts `X-Organization-Id` from proxy headers
- [ ] Pass org_id through the service layer to all database calls

### SvelteKit proxy update

- [ ] Active organization ID included in every forwarded request as `X-Organization-Id`
- [ ] Organization context available in `event.locals.organization`

## Acceptance Criteria

- A user in Org A cannot see or access dossiers belonging to Org B
- All existing tables have `organization_id` and foreign keys to user
- Free-text `reviewed_by` / `actor` fields are replaced with real user references
- Creating a dossier automatically scopes it to the active organization
- `detections` table contains no `entity_text` — only positions, types, and articles
- `documents` table contains no MinIO references — only metadata (filename, page count, status)

## Not in Scope

- Multi-org switching UI (defer to P3 — most users will have one org)
- Organization deletion with soft-delete (defer to production hardening)
