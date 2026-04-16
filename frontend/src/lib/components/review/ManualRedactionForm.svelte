<script lang="ts">
	import '@shoelace-style/shoelace/dist/components/button/button.js';

	import { onMount, onDestroy } from 'svelte';
	import type { EntityType, WooArticleCode, DetectionTier } from '$lib/types';
	import type { SelectionAnchor } from '$lib/services/selection-bbox';
	import { WOO_ARTICLES, ARTICLE_TO_ENTITY } from '$lib/utils/woo-articles';
	import { getRecentArticles, recordRecentArticle } from '$lib/services/recent-articles';
	import ArticlePicker from './ArticlePicker.svelte';

	interface Props {
		anchor: SelectionAnchor;
		stageEl: HTMLElement | null;
		scale: number;
		selectedText: string;
		/**
		 * Initial entity type. #07 uses `'area'` for shift+drag rectangles —
		 * those have no implied type from the article, so the auto-nudge
		 * article→type is suppressed while the reviewer keeps it on `area`.
		 */
		initialEntityType?: EntityType;
		onConfirm: (payload: {
			article: WooArticleCode;
			entityType: EntityType;
			tier: DetectionTier;
			motivation: string;
		}) => void;
		onCancel: () => void;
	}

	let {
		anchor,
		stageEl,
		scale,
		selectedText,
		initialEntityType,
		onConfirm,
		onCancel
	}: Props = $props();

	// See SelectionActionBar for the rationale — same page-space → viewport
	// projection so the form stays glued to the selection through scroll/zoom.
	let viewportX = $state(0);
	let viewportY = $state(0);

	function recompute() {
		if (!stageEl) return;
		const rect = stageEl.getBoundingClientRect();
		viewportX = rect.left + anchor.pdfX * scale;
		viewportY = rect.top + anchor.pdfY * scale;
	}

	$effect(() => {
		void anchor.pdfX;
		void anchor.pdfY;
		void scale;
		void stageEl;
		recompute();
	});

	// Capture the seed prop in a local const. The form is only mounted
	// per-selection, so once-off capture is exactly what we want — a later
	// prop change would not reinitialize the state, and we wouldn't want it
	// to (it'd fight the reviewer's edits mid-form).
	// svelte-ignore state_referenced_locally
	const seedEntityType = initialEntityType;
	const startedAsArea = seedEntityType === 'area';

	const recentCodes = getRecentArticles();
	const initialArticle: WooArticleCode = recentCodes[0] ?? '5.1.2e';
	let article = $state<WooArticleCode | ''>(initialArticle);
	let entityType = $state<EntityType>(
		seedEntityType ?? ARTICLE_TO_ENTITY[initialArticle] ?? 'persoon'
	);
	let motivation = $state('');

	const tierOfArticle = $derived(
		article ? WOO_ARTICLES[article as WooArticleCode].tier : ('2' as DetectionTier)
	);

	const transform = $derived(
		anchor.placement === 'above' ? 'translate(-50%, -100%)' : 'translate(-50%, 0)'
	);

	function handleConfirm() {
		if (!article) return;
		recordRecentArticle(article as WooArticleCode);
		onConfirm({
			article: article as WooArticleCode,
			entityType,
			tier: tierOfArticle,
			motivation: motivation.trim()
		});
	}

	function handleKeyDown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			e.preventDefault();
			onCancel();
		}
		// We do NOT bind Enter here — the textarea legitimately needs it.
	}

	let resizeObserver: ResizeObserver | null = null;

	onMount(() => {
		document.addEventListener('keydown', handleKeyDown);
		document.addEventListener('scroll', recompute, true);
		window.addEventListener('resize', recompute);
		if (stageEl) {
			resizeObserver = new ResizeObserver(recompute);
			resizeObserver.observe(stageEl);
		}
	});
	onDestroy(() => {
		document.removeEventListener('keydown', handleKeyDown);
		document.removeEventListener('scroll', recompute, true);
		window.removeEventListener('resize', recompute);
		resizeObserver?.disconnect();
	});
</script>

<div
	class="redaction-form"
	style="left: {viewportX}px; top: {viewportY}px; transform: {transform};"
	role="dialog"
	aria-label="Handmatige lakking"
>
	<div class="preview">
		<span class="preview-label">Selectie</span>
		{#if selectedText}
			<span class="preview-text" title={selectedText}>{selectedText}</span>
		{:else}
			<!-- #07: area selections have no selectable text — show a placeholder
			     chip so the preview row isn't visually empty. -->
			<span class="preview-placeholder">Handmatig gebied — geen tekst</span>
		{/if}
	</div>

	<ArticlePicker
		bind:article
		bind:entityType
		bind:motivation
		suppressInitialNudge={startedAsArea}
	/>

	<div class="actions">
		<sl-button size="small" variant="text" onclick={onCancel}>Annuleren</sl-button>
		<sl-button size="small" variant="primary" onclick={handleConfirm} disabled={!article}>
			Bevestigen
		</sl-button>
	</div>
</div>

<style>
	.redaction-form {
		position: fixed;
		z-index: 9999;
		width: 22rem;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		padding: 0.75rem;
		background: white;
		border: 1px solid #d1d5db;
		border-radius: 0.5rem;
		box-shadow: 0 10px 30px rgba(0, 0, 0, 0.22);
	}
	.preview {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
		padding: 0.375rem 0.5rem;
		background: #f9fafb;
		border: 1px solid #e5e7eb;
		border-radius: 0.375rem;
	}
	.preview-label {
		font-size: 0.625rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: #6b7280;
	}
	.preview-text {
		font-size: 0.8125rem;
		color: #111827;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.preview-placeholder {
		display: inline-block;
		align-self: flex-start;
		margin-top: 0.125rem;
		padding: 0.125rem 0.375rem;
		font-size: 0.6875rem;
		font-weight: 500;
		color: #4b5563;
		background: #eef2f7;
		border: 1px dashed #cbd5e1;
		border-radius: 0.25rem;
	}
	.actions {
		display: flex;
		justify-content: flex-end;
		gap: 0.5rem;
		padding-top: 0.25rem;
	}
</style>
