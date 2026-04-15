# 36 — Member Management & Invitations

- **Priority:** P2
- **Size:** M (1–3 days)
- **Source:** Auth & Billing briefing, "Invitation flow" section
- **Depends on:** #33 (Organizations), #34 (Roles)
- **Blocks:** Nothing

## Why

Real Woo workflows involve multiple people: the reviewer, a jurist who checks decisions, a supervisor who approves. The team needs to invite colleagues to their organization.

## Scope

### Invitation flow

- [ ] `/app/org/members` page — list current members with roles
- [ ] Invite form: enter email + select role → sends invitation email
- [ ] Better Auth handles the invitation lifecycle (pending → accepted)
- [ ] Recipient clicks link → creates account if needed → joins org with assigned role

### Member management

- [ ] Change a member's role (admin/owner only)
- [ ] Remove a member from the organization (admin/owner only, cannot remove last owner)
- [ ] Member list shows name, email, role, and join date

### Email

- [ ] Invitation email template in Dutch: "[Org name] nodigt je uit voor WOO Buddy"
- [ ] Requires email service to be configured (see #38, but basic SMTP works for dev)

## Acceptance Criteria

- Admin can invite a new user by email
- Invited user receives an email, can sign up, and lands in the correct organization with the correct role
- Admin can change roles and remove members
- Cannot remove the last owner

## Not in Scope

- Bulk invite (CSV upload)
- Organization switcher for multi-org users
