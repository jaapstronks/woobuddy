<script lang="ts">
	import '@shoelace-style/shoelace/dist/components/select/select.js';
	import '@shoelace-style/shoelace/dist/components/option/option.js';
	import '@shoelace-style/shoelace/dist/components/textarea/textarea.js';
	import '@shoelace-style/shoelace/dist/components/divider/divider.js';
	import '@shoelace-style/shoelace/dist/components/button/button.js';

	import { onMount, onDestroy } from 'svelte';
	import type { EntityType, WooArticleCode, DetectionTier } from '$lib/types';
	import type { SelectionAnchor } from '$lib/services/selection-bbox';
	import { WOO_ARTICLES } from '$lib/utils/woo-articles';
	import { getRecentArticles, recordRecentArticle } from '$lib/services/recent-articles';

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

	// Article implies a sensible default entity type. The reviewer can still
	// override in the entity type selector.
	const ARTICLE_TO_ENTITY: Partial<Record<WooArticleCode, EntityType>> = {
		'5.1.1e': 'bsn',
		'5.1.1d': 'gezondheid',
		'5.1.2e': 'persoon'
	};

	const ENTITY_LABELS: Record<EntityType, string> = {
		persoon: 'Persoon (naam)',
		bsn: 'BSN',
		telefoonnummer: 'Telefoonnummer',
		email: 'E-mailadres',
		adres: 'Adres',
		iban: 'IBAN',
		gezondheid: 'Gezondheidsgegeven',
		datum: 'Datum',
		geboortedatum: 'Geboortedatum',
		postcode: 'Postcode',
		kenteken: 'Kenteken',
		creditcard: 'Creditcard',
		paspoort: 'Paspoort',
		rijbewijs: 'Rijbewijs',
		kvk: 'KvK-nummer',
		btw: 'BTW-nummer',
		area: 'Handmatig gebied',
		custom: 'Zoekterm (eigen lijst)'
	};

	// Group articles by tier; within a tier, sort by code. Recent articles
	// appear as a separate group pinned to the top.
	const recentCodes = $state(getRecentArticles());
	const allArticles = Object.values(WOO_ARTICLES);
	const byTier = {
		'1': allArticles.filter((a) => a.tier === '1').sort((a, b) => a.code.localeCompare(b.code)),
		'2': allArticles.filter((a) => a.tier === '2').sort((a, b) => a.code.localeCompare(b.code)),
		'3': allArticles.filter((a) => a.tier === '3').sort((a, b) => a.code.localeCompare(b.code))
	};

	// Capture the seed prop in a local const. The form is only mounted
	// per-selection, so once-off capture is exactly what we want — a later
	// prop change would not reinitialize the state, and we wouldn't want it
	// to (it'd fight the reviewer's edits mid-form).
	// svelte-ignore state_referenced_locally
	const seedEntityType = initialEntityType;
	const startedAsArea = seedEntityType === 'area';

	const initialArticle: WooArticleCode = recentCodes[0] ?? '5.1.2e';
	let article = $state<WooArticleCode | ''>(initialArticle);
	let entityType = $state<EntityType>(
		seedEntityType ?? ARTICLE_TO_ENTITY[initialArticle] ?? 'persoon'
	);
	let motivation = $state('');

	// Pre-fill the motivation template whenever the article changes.
	$effect(() => {
		if (!article) return;
		const info = WOO_ARTICLES[article as WooArticleCode];
		motivation = `Informatie valt onder Art. ${info.code} Woo — ${info.ground}.`;
	});

	// When article changes, also nudge the entity type if the new article
	// implies a different one — but only if the reviewer hasn't manually
	// overridden it since the last change (tracked via `userTouchedType`).
	// Area flows start with `userTouchedType = true` so the nudge is inert
	// until the reviewer explicitly picks a different type.
	let userTouchedType = $state(startedAsArea);
	$effect(() => {
		if (!article || userTouchedType) return;
		const implied = ARTICLE_TO_ENTITY[article as WooArticleCode];
		if (implied) entityType = implied;
	});

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

	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<!-- svelte-ignore a11y_label_has_associated_control -->
	<sl-select
		label="Woo-grond"
		size="small"
		value={article}
		onsl-change={(e: Event) => {
			article = ((e.target as HTMLSelectElement).value || '') as WooArticleCode | '';
			userTouchedType = false;
		}}
	>
		{#if recentCodes.length > 0}
			<small slot="label-suffix">&nbsp;</small>
			<sl-option disabled>— Recent gebruikt —</sl-option>
			{#each recentCodes as code}
				{#if WOO_ARTICLES[code]}
					<sl-option value={code}>
						Tier {WOO_ARTICLES[code].tier} · {code} — {WOO_ARTICLES[code].ground}
					</sl-option>
				{/if}
			{/each}
			<sl-divider></sl-divider>
		{/if}
		<sl-option disabled>— Tier 1 (harde identifiers) —</sl-option>
		{#each byTier['1'] as art}
			<sl-option value={art.code}>{art.code} — {art.ground}</sl-option>
		{/each}
		<sl-option disabled>— Tier 2 (persoonsgegevens) —</sl-option>
		{#each byTier['2'] as art}
			<sl-option value={art.code}>{art.code} — {art.ground}</sl-option>
		{/each}
		<sl-option disabled>— Tier 3 (inhoudelijk) —</sl-option>
		{#each byTier['3'] as art}
			<sl-option value={art.code}>{art.code} — {art.ground}</sl-option>
		{/each}
	</sl-select>

	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<!-- svelte-ignore a11y_label_has_associated_control -->
	<sl-select
		label="Type"
		size="small"
		value={entityType}
		onsl-change={(e: Event) => {
			entityType = (e.target as HTMLSelectElement).value as EntityType;
			userTouchedType = true;
		}}
	>
		{#each Object.entries(ENTITY_LABELS) as [value, label]}
			<sl-option value={value}>{label}</sl-option>
		{/each}
	</sl-select>

	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<!-- svelte-ignore a11y_label_has_associated_control -->
	<sl-textarea
		label="Motivering"
		size="small"
		rows="2"
		value={motivation}
		onsl-input={(e: Event) => { motivation = (e.target as HTMLTextAreaElement).value; }}
	></sl-textarea>

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
