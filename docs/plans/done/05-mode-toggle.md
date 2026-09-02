# 09 — Review/Edit Mode Toggle

- **Priority:** P1
- **Size:** M (1–3 days)
- **Source:** Editing briefing, "Two Modes, One Viewer" section
- **Depends on:** Nothing (existing PdfViewer)
- **Blocks:** #06, #07, #11, #12

## Why

The current PdfViewer only supports Review Mode (clicking detections, sidebar-driven). Real Woo reviewers need to directly interact with the PDF to add, adjust, and refine redactions. The mode toggle is the gateway to all manual editing features.

## Assessment

The briefing's design is clean: same viewer, same overlays, different cursor behavior and click semantics. The distinction is primarily UX, not architectural.

**Adopt as-is.** The mode toggle is a prerequisite for all other editing features — build it first, even before the editing features themselves are ready.

## Scope

### Toolbar

- [ ] Add mode toggle buttons to PdfViewer toolbar: "Beoordelen" (Review) / "Bewerken" (Edit)
- [ ] Active mode has a distinct visual style (different background, clear label)
- [ ] Keyboard shortcut: `M` toggles between modes
- [ ] Toolbar subtly changes appearance per mode (e.g., thin blue top-border in Edit Mode)

### Cursor behavior

- [ ] Review Mode: pointer cursor. Click on overlay → select detection in sidebar. Click empty space → deselect.
- [ ] Edit Mode: crosshair cursor (default), I-beam when hovering selectable text layer spans
- [ ] Mode state stored in a Svelte `$state` rune, shared between PdfViewer and sidebar

### Sidebar adaptation

- [ ] Review Mode sidebar: unchanged (current behavior)
- [ ] Edit Mode sidebar: contextual — shows detection list by default, switches to edit controls when something is selected in the PDF
- [ ] Switching modes does not lose sidebar scroll position or filter state

### Instant switching

- [ ] No modal, no confirmation — instant toggle
- [ ] Both modes show identical PDF rendering and detection overlays

## Acceptance Criteria

- `M` key toggles modes, toolbar visually updates
- Cursor changes between pointer and crosshair/I-beam
- Sidebar content adapts to the active mode
- No state loss when switching modes

## Not in Scope

- Actual editing functionality (text selection, area selection, boundary adjustment — those are separate todos)
- Edit Mode toolbar tools beyond the mode indicator
