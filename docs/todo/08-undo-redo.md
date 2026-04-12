# 13 — Undo/Redo

- **Priority:** P1
- **Size:** M (1–3 days)
- **Source:** Editing briefing, "Feature 7: Undo/Redo" section
- **Depends on:** #05 (Mode toggle)
- **Blocks:** Nothing, but benefits all editing features

## Why

In a tool where a misclick can redact the wrong passage, undo is fundamental. Without it, reviewers will be afraid to experiment, slowing down their workflow.

## Scope

### Command-based undo stack

- [ ] Maintain an undo stack per document per session (in-memory, not persisted)
- [ ] Each action is a reversible command: `{ type, forward(), reverse() }`
- [ ] Stack clears when document is closed or session ends

### Keyboard shortcuts

- [ ] `Ctrl+Z` — undo last action
- [ ] `Ctrl+Shift+Z` / `Ctrl+Y` — redo
- [ ] Undo/redo buttons in toolbar (when in Edit Mode)

### Undoable actions

- [ ] Add manual redaction (text or area)
- [ ] Accept/reject detection
- [ ] Boundary adjustment (when implemented)
- [ ] Split/merge (when implemented)
- [ ] Mark page complete (when implemented)
- [ ] Search-and-redact batch (undoes the entire batch as one action)

### Visual feedback

- [ ] On undo: briefly flash the affected area in the PDF (300ms yellow highlight pulse → fade)
- [ ] CSS-only animation

### Audit log behavior

- [ ] Audit log is NOT affected by undo — it records both the original action AND the undo
- [ ] Full trail preserved regardless of undo/redo

## Acceptance Criteria

- `Ctrl+Z` undoes the last redaction action instantly (no confirmation)
- `Ctrl+Shift+Z` redoes it
- Undo flash animation briefly highlights the affected area
- Audit log shows both the action and its undo as separate entries
- Stack is per-document, per-session — doesn't persist across page reloads

## Not in Scope

- Persistent undo history (across sessions)
- Collaborative undo (multi-user awareness)
