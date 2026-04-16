<script lang="ts">
	import '@shoelace-style/shoelace/dist/components/input/input.js';
	import '@shoelace-style/shoelace/dist/components/button/button.js';
	import '@shoelace-style/shoelace/dist/components/dialog/dialog.js';
	import type SlInput from '@shoelace-style/shoelace/dist/components/input/input.js';

	import { onMount } from 'svelte';
	import { Search, X, CheckSquare, Square } from 'lucide-svelte';
	import { searchStore } from '$lib/stores/search.svelte';
	import { WOO_ARTICLES, ARTICLE_TO_ENTITY } from '$lib/utils/woo-articles';
	import { getRecentArticles, recordRecentArticle } from '$lib/services/recent-articles';
	import type { EntityType, WooArticleCode, DetectionTier } from '$lib/types';
	import type { SearchOccurrence } from '$lib/services/search-redact';
	import { highlightedContext } from '$lib/utils/search-context';
	import ArticlePicker from './ArticlePicker.svelte';

	interface Props {
		onClose: () => void;
		onJumpToOccurrence: (occ: SearchOccurrence) => void;
		onRedactOccurrences: (payload: {
			occurrences: SearchOccurrence[];
			article: WooArticleCode;
			entityType: EntityType;
			tier: DetectionTier;
			motivation: string;
		}) => Promise<void>;
	}

	let { onClose, onJumpToOccurrence, onRedactOccurrences }: Props = $props();

	let inputEl = $state<SlInput | null>(null);
	let pickerOpen = $state(false);
	let pickerTargets = $state<SearchOccurrence[]>([]);
	let submitting = $state(false);

	// Picker form state — managed by the ArticlePicker child, bound here
	// so confirmPicker() can read them at submit time.
	const recentCodes = getRecentArticles();
	const initialArticle: WooArticleCode = recentCodes[0] ?? '5.1.2e';
	let article = $state<WooArticleCode>(initialArticle);
	let entityType = $state<EntityType>(ARTICLE_TO_ENTITY[initialArticle] ?? 'persoon');
	let motivation = $state('');

	const tierOfArticle = $derived<DetectionTier>(
		WOO_ARTICLES[article].tier as DetectionTier
	);

	onMount(() => {
		// Focus the input once Shoelace has hydrated. The custom element needs
		// a tick before its internal native input is ready to receive focus.
		queueMicrotask(() => {
			inputEl?.focus();
		});
	});

	function handleKeyDown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			e.preventDefault();
			if (pickerOpen) {
				pickerOpen = false;
				return;
			}
			onClose();
		}
	}

	function openPickerForAll() {
		pickerTargets = searchStore.redactable;
		if (pickerTargets.length === 0) return;
		pickerOpen = true;
	}

	function openPickerForSelected() {
		pickerTargets = searchStore.getSelectedOccurrences();
		if (pickerTargets.length === 0) return;
		pickerOpen = true;
	}

	async function confirmPicker() {
		if (!article || pickerTargets.length === 0) return;
		submitting = true;
		try {
			recordRecentArticle(article);
			await onRedactOccurrences({
				occurrences: pickerTargets,
				article,
				entityType,
				tier: tierOfArticle,
				motivation: motivation.trim()
			});
			pickerOpen = false;
			pickerTargets = [];
			// Clear the current selection — those rows are now `alreadyRedacted`
			// and the next query re-flags them. Keeping the selection would
			// confuse the counts.
			searchStore.clearSelection();
		} finally {
			submitting = false;
		}
	}

	const occContext = (occ: SearchOccurrence) => highlightedContext(occ.context, occ.matchText);

	// Reactive shortcut references for the template.
	const resultCount = $derived(searchStore.redactable.length);
	const alreadyCount = $derived(searchStore.alreadyRedacted.length);
	const selectedCount = $derived(searchStore.effectiveSelectedCount);
	const allSelected = $derived(
		resultCount > 0 && selectedCount === resultCount
	);
</script>

<svelte:window onkeydown={handleKeyDown} />

<div class="search-panel">
	<div class="search-header">
		<div class="flex items-center gap-2">
			<Search size={14} class="text-neutral" />
			<span class="text-[11px] font-semibold uppercase tracking-wide text-primary">
				Zoek & Lak
			</span>
		</div>
		<button
			type="button"
			class="rounded p-1 text-neutral hover:bg-gray-100"
			title="Sluiten (Esc)"
			aria-label="Sluiten"
			onclick={onClose}
		>
			<X size={14} />
		</button>
	</div>

	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<!-- svelte-ignore a11y_label_has_associated_control -->
	<sl-input
		bind:this={inputEl}
		size="small"
		placeholder="Zoek tekst..."
		value={searchStore.query}
		clearable
		onsl-input={(e: Event) => searchStore.setQuery((e.target as HTMLInputElement).value)}
	></sl-input>

	{#if searchStore.query.trim().length > 0 && searchStore.query.trim().length < 2}
		<p class="mt-2 text-[11px] text-neutral">Typ ten minste 2 tekens.</p>
	{:else if searchStore.query.trim().length >= 2}
		<div class="mt-2 flex items-center justify-between text-[11px] text-neutral">
			<span>
				<strong class="text-gray-800">{resultCount}</strong>
				{resultCount === 1 ? 'resultaat' : 'resultaten'}
				{#if alreadyCount > 0}
					· {alreadyCount} al gelakt
				{/if}
			</span>
			{#if resultCount > 0}
				<button
					type="button"
					class="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium text-primary hover:bg-primary/10"
					onclick={() => (allSelected ? searchStore.clearSelection() : searchStore.selectAll())}
				>
					{#if allSelected}
						<CheckSquare size={12} />
						Alles deselecteren
					{:else}
						<Square size={12} />
						Alles selecteren
					{/if}
				</button>
			{/if}
		</div>
	{/if}

	{#if resultCount > 0}
		<div class="mt-2 flex items-center gap-1.5">
			<sl-button size="small" variant="primary" onclick={openPickerForAll}>
				Lak alles ({resultCount})
			</sl-button>
			<sl-button
				size="small"
				variant="default"
				disabled={selectedCount === 0}
				onclick={openPickerForSelected}
			>
				Lak geselecteerde ({selectedCount})
			</sl-button>
		</div>
	{/if}

	<div class="mt-3 flex-1 overflow-y-auto">
		{#if searchStore.query.trim().length >= 2 && resultCount === 0 && alreadyCount === 0}
			<p class="text-xs text-neutral">Geen resultaten gevonden.</p>
		{/if}

		{#if resultCount > 0}
			<ul class="space-y-1">
				{#each searchStore.redactable as occ (occ.id)}
					{@const parts = occContext(occ)}
					{@const isSelected = searchStore.selectedIds.has(occ.id)}
					{@const isFocused = searchStore.focusedId === occ.id}
					<li
						class="occ-row"
						class:occ-focused={isFocused}
						class:occ-selected={isSelected}
					>
						<label class="occ-check">
							<input
								type="checkbox"
								checked={isSelected}
								onchange={() => searchStore.toggleSelected(occ.id)}
							/>
						</label>
						<button
							type="button"
							class="occ-body"
							onclick={() => {
								searchStore.focus(occ.id);
								onJumpToOccurrence(occ);
							}}
						>
							<span class="occ-page">p.{occ.page + 1}</span>
							<span class="occ-context">
								<span class="dim">{parts.before}</span><mark>{parts.match}</mark><span class="dim">{parts.after}</span>
							</span>
						</button>
					</li>
				{/each}
			</ul>
		{/if}

		{#if alreadyCount > 0}
			<details class="mt-3">
				<summary class="cursor-pointer text-[11px] font-medium text-neutral hover:text-gray-800">
					Al gelakt ({alreadyCount})
				</summary>
				<ul class="mt-1 space-y-1">
					{#each searchStore.alreadyRedacted as occ (occ.id)}
						{@const parts = occContext(occ)}
						<li class="occ-row occ-muted">
							<span class="occ-check"></span>
							<button
								type="button"
								class="occ-body"
								onclick={() => {
									searchStore.focus(occ.id);
									onJumpToOccurrence(occ);
								}}
							>
								<span class="occ-page">p.{occ.page + 1}</span>
								<span class="occ-context">
									<span class="dim">{parts.before}</span><mark>{parts.match}</mark><span class="dim">{parts.after}</span>
								</span>
							</button>
						</li>
					{/each}
				</ul>
			</details>
		{/if}
	</div>
</div>

<!-- Shared article-picker dialog. Opened for both "Lak alles" and "Lak
     geselecteerde" — the difference is only in which occurrences get
     passed to `onRedactOccurrences`. -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<sl-dialog
	label={pickerTargets.length === searchStore.redactable.length
		? `Alles lakken (${pickerTargets.length})`
		: `Geselecteerde lakken (${pickerTargets.length})`}
	open={pickerOpen}
	onsl-request-close={() => {
		if (!submitting) pickerOpen = false;
	}}
>
	<div class="space-y-3">
		<ArticlePicker bind:article bind:entityType bind:motivation />
	</div>
	<sl-button slot="footer" variant="text" onclick={() => (pickerOpen = false)} disabled={submitting}>
		Annuleren
	</sl-button>
	<sl-button slot="footer" variant="primary" onclick={confirmPicker} disabled={submitting || !article}>
		{#if submitting}
			Bezig...
		{:else}
			Bevestigen ({pickerTargets.length})
		{/if}
	</sl-button>
</sl-dialog>

<style>
	.search-panel {
		display: flex;
		flex-direction: column;
		padding: 0.75rem 1rem;
		border-bottom: 1px solid #e5e7eb;
		background: white;
		max-height: 28rem;
	}
	.search-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 0.5rem;
	}

	.occ-row {
		display: flex;
		align-items: flex-start;
		gap: 0.375rem;
		padding: 0.25rem 0.375rem;
		border-radius: 0.25rem;
		transition: background-color 120ms;
	}
	.occ-row:hover {
		background: #f3f4f6;
	}
	.occ-focused {
		background: rgba(250, 204, 21, 0.12);
		outline: 1px solid rgba(250, 204, 21, 0.4);
	}
	.occ-selected {
		background: rgba(27, 79, 114, 0.06);
	}
	.occ-muted {
		opacity: 0.55;
	}
	.occ-check {
		display: flex;
		align-items: center;
		padding-top: 0.125rem;
		width: 1rem;
		flex-shrink: 0;
	}
	.occ-check input {
		cursor: pointer;
	}
	.occ-body {
		display: flex;
		align-items: flex-start;
		gap: 0.375rem;
		flex: 1;
		text-align: left;
		padding: 0;
		background: transparent;
		border: none;
		cursor: pointer;
		min-width: 0;
	}
	.occ-page {
		flex-shrink: 0;
		padding: 0 0.3rem;
		font-size: 10px;
		font-weight: 600;
		color: #4b5563;
		background: #e5e7eb;
		border-radius: 0.25rem;
		line-height: 1.1rem;
	}
	.occ-context {
		flex: 1;
		min-width: 0;
		font-size: 11px;
		line-height: 1.3;
		color: #374151;
		word-break: break-word;
	}
	.occ-context .dim {
		color: #9ca3af;
	}
	.occ-context mark {
		background: rgba(250, 204, 21, 0.55);
		color: #111827;
		padding: 0 1px;
		border-radius: 2px;
	}
</style>
