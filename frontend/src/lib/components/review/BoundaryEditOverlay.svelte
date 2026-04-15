<script lang="ts">
	import type { BoundingBox } from '$lib/types';

	/**
	 * Boundary adjustment draft overlay (#11). Renders the in-progress edit
	 * box(es) for a single detection above the text layer with eight resize
	 * handles per box and a floating Save / Cancel toolbar above the primary
	 * box. Pure presentation: PdfViewer owns all editing state and emits the
	 * actual `onBoundaryAdjust` to the parent.
	 *
	 * The box itself is `pointer-events: none` so Shift/Alt+click on words
	 * underneath the draft (for text-based extend/shrink) still reaches the
	 * text layer. Only handles capture the mouse.
	 */

	export type HandleDir = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w';
	const HANDLE_DIRS: HandleDir[] = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];

	interface Props {
		editingBboxes: BoundingBox[];
		currentPage: number;
		scale: number;
		onHandleMouseDown: (event: MouseEvent, boxIndex: number, dir: HandleDir) => void;
		onCommit: () => void;
		onCancel: () => void;
	}

	let { editingBboxes, currentPage, scale, onHandleMouseDown, onCommit, onCancel }: Props =
		$props();

	const primary = $derived(editingBboxes.find((b) => b.page === currentPage));
</script>

{#each editingBboxes as b, i (i)}
	{#if b.page === currentPage}
		<div
			class="edit-box"
			style="left: {b.x0 * scale}px; top: {b.y0 * scale}px; width: {(b.x1 - b.x0) *
				scale}px; height: {(b.y1 - b.y0) * scale}px;"
		>
			{#each HANDLE_DIRS as dir (dir)}
				<button
					type="button"
					class="edit-handle handle-{dir}"
					aria-label="Grens aanpassen ({dir})"
					onmousedown={(e) => onHandleMouseDown(e, i, dir)}
				></button>
			{/each}
		</div>
	{/if}
{/each}
{#if primary}
	<div
		class="edit-toolbar"
		style="left: {primary.x0 * scale}px; top: {Math.max(0, primary.y0 * scale - 34)}px;"
	>
		<button
			type="button"
			class="edit-toolbar-btn edit-toolbar-save"
			title="Opslaan (Enter)"
			onclick={onCommit}
		>
			Opslaan
		</button>
		<button type="button" class="edit-toolbar-btn" title="Annuleren (Escape)" onclick={onCancel}>
			Annuleren
		</button>
	</div>
{/if}

<style>
	/* The draft box sits above the text layer and above detection overlays
	   so its handles are always hit-testable. The box itself is inert
	   (pointer-events: none) — only the handles capture mouse events, so
	   Shift/Alt+click on words underneath the box (for text-based
	   extend/shrink) still reaches the text layer. */
	.edit-box {
		position: absolute;
		z-index: 5;
		pointer-events: none;
		border: 2px solid var(--color-primary, #1b4f72);
		background: rgba(27, 79, 114, 0.08);
		border-radius: 2px;
	}
	.edit-handle {
		position: absolute;
		width: 10px;
		height: 10px;
		padding: 0;
		margin: 0;
		background: white;
		border: 2px solid var(--color-primary, #1b4f72);
		border-radius: 1px;
		pointer-events: auto;
		box-sizing: border-box;
	}
	/* Corner handles. Each handle is nudged so its center sits exactly on
	   the box corner (half the handle size = 5px). */
	.handle-nw {
		left: -6px;
		top: -6px;
		cursor: nwse-resize;
	}
	.handle-ne {
		right: -6px;
		top: -6px;
		cursor: nesw-resize;
	}
	.handle-se {
		right: -6px;
		bottom: -6px;
		cursor: nwse-resize;
	}
	.handle-sw {
		left: -6px;
		bottom: -6px;
		cursor: nesw-resize;
	}
	/* Edge handles — positioned on the midpoint of each edge. */
	.handle-n {
		left: 50%;
		top: -6px;
		transform: translateX(-50%);
		cursor: ns-resize;
	}
	.handle-s {
		left: 50%;
		bottom: -6px;
		transform: translateX(-50%);
		cursor: ns-resize;
	}
	.handle-e {
		right: -6px;
		top: 50%;
		transform: translateY(-50%);
		cursor: ew-resize;
	}
	.handle-w {
		left: -6px;
		top: 50%;
		transform: translateY(-50%);
		cursor: ew-resize;
	}
	/* Floating Save/Cancel toolbar above the primary draft bbox. */
	.edit-toolbar {
		position: absolute;
		z-index: 6;
		display: inline-flex;
		gap: 0.25rem;
		padding: 0.25rem;
		border-radius: 0.375rem;
		background: white;
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.18);
	}
	.edit-toolbar-btn {
		padding: 0.25rem 0.6rem;
		font-size: 0.72rem;
		font-weight: 600;
		border-radius: 0.25rem;
		border: 1px solid #d1d5db;
		background: white;
		color: #374151;
		cursor: pointer;
	}
	.edit-toolbar-btn:hover {
		background: #f3f4f6;
	}
	.edit-toolbar-save {
		background: var(--color-primary, #1b4f72);
		color: white;
		border-color: var(--color-primary, #1b4f72);
	}
	.edit-toolbar-save:hover {
		background: #143a57;
	}
</style>
