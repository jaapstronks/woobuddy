# 34 — Roles & Permissions

- **Priority:** P1
- **Size:** M (1–3 days)
- **Source:** Auth & Billing briefing, "Roles and permissions" section
- **Depends on:** #33 (Organizations)
- **Blocks:** Nothing directly

## Why

The multi-user workflows described in the briefings (reviewer, jurist/supervisor, viewer) need role-based access. A viewer shouldn't be able to modify redaction decisions. A reviewer shouldn't manage billing.

## Assessment

The four-role model (owner, admin, reviewer, viewer) is appropriate. Better Auth's organization plugin supports custom roles and permissions natively — no custom RBAC system needed.

**Adopt as-is.**

## Scope

### Role definitions

- [ ] Configure Better Auth organization plugin with four roles:
  - `owner` — full access including billing
  - `admin` — full access except billing
  - `reviewer` — create dossiers, review detections, cannot approve or manage members
  - `viewer` — read-only access
- [ ] First user in an organization automatically gets `owner` role

### Frontend enforcement

- [ ] Role-aware UI: hide/disable actions the user's role cannot perform
- [ ] Viewers see read-only review interface (no accept/reject buttons). Note: viewers still need the PDF in their own browser to see document content — the server only provides detection metadata.
- [ ] Only admin/owner see member management and settings pages
- [ ] Only owner sees billing page

### Backend enforcement

- [ ] FastAPI middleware checks permissions on write operations
- [ ] Approve/reopen endpoints require admin or owner role
- [ ] Member management endpoints require admin or owner role
- [ ] Read endpoints accessible to all roles within the organization

## Acceptance Criteria

- A viewer can browse dossiers and detections but cannot accept/reject
- A reviewer can review but cannot approve documents or manage members
- An admin can do everything except billing
- Backend rejects unauthorized actions with 403, not just hidden UI

## Not in Scope

- Granular per-dossier permissions (e.g., assigning specific reviewers to specific dossiers)
- Audit of permission changes
