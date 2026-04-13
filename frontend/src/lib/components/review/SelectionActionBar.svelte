<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import type { SelectionAnchor } from '$lib/services/selection-bbox';

	interface Props {
		anchor: SelectionAnchor;
		stageEl: HTMLElement | null;
		scale: number;
		onConfirm: () => void;
		onCancel: () => void;
	}

	let { anchor, stageEl, scale, onConfirm, onCancel }: Props = $props();

	let barEl = $state<HTMLDivElement | null>(null);

	// We position the bar `fixed` in viewport coordinates, but derive those
	// coordinates fresh from the pdf-stage element's current bounding rect.
	// That means the bar stays pinned to the selection while the reviewer
	// scrolls any ancestor scroller, zooms the PDF (scale changes), or
	// resizes the window — without needing a scroll listener on a specific
	// scroller or holding a live DOM Range.
	let viewportX = $state(0);
	let viewportY = $state(0);

	function recompute() {
		if (!stageEl) return;
		const rect = stageEl.getBoundingClientRect();
		viewportX = rect.left + anchor.pdfX * scale;
		viewportY = rect.top + anchor.pdfY * scale;
	}

	$effect(() => {
		// Reactive deps: rerun when anchor, scale, or stage changes.
		void anchor.pdfX;
		void anchor.pdfY;
		void scale;
		void stageEl;
		recompute();
	});

	// The bar is `position: fixed` so we work entirely in viewport coordinates.
	// `translate(-50%, -100%)` centers horizontally on the anchor and places
	// the bottom edge on the anchor point when placement is "above"; for
	// "below" we drop the -100% so the top edge sits on the anchor.
	const transform = $derived(
		anchor.placement === 'above' ? 'translate(-50%, -100%)' : 'translate(-50%, 0)'
	);

	// Dismiss on outside click or Escape.
	function handleDocumentMouseDown(e: MouseEvent) {
		if (!barEl) return;
		if (barEl.contains(e.target as Node)) return;
		// Clicks inside the text layer that created a new selection should
		// NOT dismiss — the parent will push a new anchor. We detect this by
		// looking for a text layer ancestor.
		const target = e.target as HTMLElement | null;
		if (target?.closest('.textLayer')) return;
		onCancel();
	}

	function handleKeyDown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			e.preventDefault();
			onCancel();
		} else if (e.key === 'Enter') {
			e.preventDefault();
			onConfirm();
		}
	}

	let resizeObserver: ResizeObserver | null = null;

	onMount(() => {
		document.addEventListener('mousedown', handleDocumentMouseDown);
		document.addEventListener('keydown', handleKeyDown);
		// Capture-phase scroll: fires for *any* ancestor scroller, so we
		// don't need to know which one holds the PDF.
		document.addEventListener('scroll', recompute, true);
		window.addEventListener('resize', recompute);
		if (stageEl) {
			resizeObserver = new ResizeObserver(recompute);
			resizeObserver.observe(stageEl);
		}
	});

	onDestroy(() => {
		document.removeEventListener('mousedown', handleDocumentMouseDown);
		document.removeEventListener('keydown', handleKeyDown);
		document.removeEventListener('scroll', recompute, true);
		window.removeEventListener('resize', recompute);
		resizeObserver?.disconnect();
	});
</script>

<div
	bind:this={barEl}
	class="action-bar"
	style="left: {viewportX}px; top: {viewportY}px; transform: {transform};"
	role="toolbar"
	aria-label="Selectie acties"
>
	<button type="button" class="primary" onclick={onConfirm}>
		Lakken
	</button>
	<button type="button" class="ghost" onclick={onCancel}>
		Annuleren
	</button>
</div>

<style>
	.action-bar {
		position: fixed;
		z-index: 9999;
		display: inline-flex;
		gap: 0.25rem;
		padding: 0.25rem;
		background: white;
		border: 1px solid #d1d5db;
		border-radius: 0.5rem;
		box-shadow: 0 6px 20px rgba(0, 0, 0, 0.18);
		white-space: nowrap;
	}
	button {
		font-size: 0.8125rem;
		font-weight: 500;
		padding: 0.375rem 0.75rem;
		border-radius: 0.375rem;
		border: none;
		cursor: pointer;
		transition: background-color 120ms;
	}
	button.primary {
		background: var(--color-primary, #1b4f72);
		color: white;
	}
	button.primary:hover {
		background: #164360;
	}
	button.ghost {
		background: transparent;
		color: #4b5563;
	}
	button.ghost:hover {
		background: #f3f4f6;
	}
</style>
