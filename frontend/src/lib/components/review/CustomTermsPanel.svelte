<script lang="ts">
	import '@shoelace-style/shoelace/dist/components/input/input.js';
	import '@shoelace-style/shoelace/dist/components/button/button.js';
	import '@shoelace-style/shoelace/dist/components/badge/badge.js';
	import '@shoelace-style/shoelace/dist/components/spinner/spinner.js';
	import '@shoelace-style/shoelace/dist/components/tooltip/tooltip.js';
	import '@shoelace-style/shoelace/dist/components/select/select.js';
	import '@shoelace-style/shoelace/dist/components/option/option.js';

	import { customTermsStore } from '$lib/stores/custom-terms.svelte';
	import { ChevronDown, ChevronRight, Search, Trash2 } from 'lucide-svelte';

	interface Props {
		/** Called after a successful add — the review page then re-runs
		 *  `/api/analyze` with the updated wordlist. */
		onAdd: (term: string, wooArticle: string) => Promise<void> | void;
		/** Called after a successful remove — same re-analysis trigger. */
		onRemove: (id: string, term: string) => Promise<void> | void;
		/**
		 * Count of currently active `custom` detections per term id.
		 * The review page computes this from `detectionStore.all` and
		 * passes it in so the panel can show "4 gevonden" next to each
		 * row without having to reach into the detection store itself.
		 * Indexed by term string (the normalized form) — the matcher
		 * produces one detection per occurrence, so the count equals
		 * the number of matches.
		 */
		matchCounts?: Record<string, number>;
	}

	let { onAdd, onRemove, matchCounts = {} }: Props = $props();

	// Collapsed by default — reviewers who never touch the feature
	// shouldn't see a crowded sidebar on first load. Same UX as the
	// reference-names panel so the two sibling sections behave
	// identically.
	let expanded = $state(false);
	let newTerm = $state('');
	let newArticle = $state('5.1.2e');
	let submitting = $state(false);

	const count = $derived(customTermsStore.count);

	async function handleAdd() {
		const trimmed = newTerm.trim();
		if (!trimmed || submitting) return;
		submitting = true;
		try {
			await onAdd(trimmed, newArticle);
			newTerm = '';
		} finally {
			submitting = false;
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			e.preventDefault();
			void handleAdd();
		}
	}

	async function handleRemove(id: string, term: string) {
		if (submitting) return;
		submitting = true;
		try {
			await onRemove(id, term);
		} finally {
			submitting = false;
		}
	}

	// Match count lookup is keyed on the normalized term so the panel
	// stays consistent with the backend matcher — the review page
	// normalizes the detection reasoning once and feeds this map in.
	function countFor(normalized: string): number {
		return matchCounts[normalized] ?? 0;
	}
</script>

<div class="border-b border-gray-200 bg-white">
	<button
		type="button"
		class="flex w-full items-center gap-2 px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-primary hover:bg-gray-50"
		onclick={() => (expanded = !expanded)}
		aria-expanded={expanded}
	>
		{#if expanded}
			<ChevronDown size={14} />
		{:else}
			<ChevronRight size={14} />
		{/if}
		<Search size={14} />
		<span class="flex-1">Eigen zoektermen</span>
		{#if count > 0}
			<sl-badge variant="neutral" pill>{count}</sl-badge>
		{/if}
	</button>

	{#if expanded}
		<div class="px-4 pb-3">
			<p class="mb-3 text-[11px] leading-relaxed text-neutral">
				Termen die in dit document overal gelakt moeten worden (bijv. bedrijfsnaam, codenaam).
				Werkt alleen voor dit document.
			</p>

			<div class="mb-2 flex items-center gap-2">
				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<sl-input
					size="small"
					placeholder="Bijv. Project Apollo"
					value={newTerm}
					disabled={submitting}
					onsl-input={(e: Event) => {
						newTerm = (e.target as HTMLInputElement).value;
					}}
					onkeydown={handleKeydown}
					style="flex: 1; min-width: 0;"
				></sl-input>
				<sl-button
					size="small"
					variant="primary"
					disabled={submitting || !newTerm.trim()}
					onclick={handleAdd}
				>
					Toevoegen
				</sl-button>
			</div>

			<div class="mb-2">
				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<sl-select
					size="small"
					label="Woo-artikel"
					value={newArticle}
					onsl-change={(e: Event) => {
						newArticle = (e.target as HTMLSelectElement).value;
					}}
				>
					<sl-option value="5.1.2e">5.1.2e — persoonsgegevens</sl-option>
					<sl-option value="5.1.2b">5.1.2b — bedrijfsgegevens</sl-option>
					<sl-option value="5.1.2c">5.1.2c — toezicht/controle</sl-option>
					<sl-option value="5.1.2i">5.1.2i — onevenredig nadeel</sl-option>
				</sl-select>
			</div>

			{#if customTermsStore.error}
				<div class="mb-2 rounded border border-red-200 bg-red-50 px-2 py-1 text-[11px] text-red-700">
					{customTermsStore.error}
					<button
						type="button"
						class="ml-2 underline"
						onclick={() => customTermsStore.clearError()}
					>
						sluiten
					</button>
				</div>
			{/if}

			{#if customTermsStore.loading && count === 0}
				<div class="flex items-center gap-2 text-[11px] text-neutral">
					<sl-spinner style="font-size: 0.75rem;"></sl-spinner>
					Lijst laden...
				</div>
			{:else if count === 0}
				<div class="rounded border border-dashed border-gray-200 px-2 py-3 text-center text-[11px] text-neutral">
					Nog geen zoektermen op de lijst.
				</div>
			{:else}
				<ul class="flex flex-col gap-1">
					{#each customTermsStore.terms as t (t.id)}
						{@const hits = countFor(t.normalized_term)}
						<li
							class="flex items-center gap-2 rounded border border-gray-200 bg-gray-50 px-2 py-1 text-xs"
						>
							<span class="flex-1 truncate" title={t.term}>
								{t.term}
							</span>
							<span class="shrink-0 text-[10px] text-neutral">
								{hits} gevonden
							</span>
							<sl-tooltip content="Verwijder zoekterm">
								<button
									type="button"
									class="rounded p-1 text-neutral hover:bg-red-100 hover:text-red-700 disabled:opacity-50"
									disabled={submitting}
									aria-label="Verwijder {t.term}"
									onclick={() => handleRemove(t.id, t.term)}
								>
									<Trash2 size={12} />
								</button>
							</sl-tooltip>
						</li>
					{/each}
				</ul>
			{/if}
		</div>
	{/if}
</div>
