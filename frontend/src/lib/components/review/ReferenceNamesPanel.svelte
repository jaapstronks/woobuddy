<script lang="ts">
	import '@shoelace-style/shoelace/dist/components/input/input.js';
	import '@shoelace-style/shoelace/dist/components/button/button.js';
	import '@shoelace-style/shoelace/dist/components/badge/badge.js';
	import '@shoelace-style/shoelace/dist/components/spinner/spinner.js';
	import '@shoelace-style/shoelace/dist/components/tooltip/tooltip.js';

	import { referenceNamesStore } from '$lib/stores/reference-names.svelte';
	import { ChevronDown, ChevronRight, Trash2, UserCheck } from 'lucide-svelte';

	interface Props {
		/** Called after a successful add — the review page then re-runs
		 *  `/api/analyze` with the updated list. */
		onAdd: (displayName: string) => Promise<void> | void;
		/** Called after a successful remove — same re-analysis trigger. */
		onRemove: (id: string, displayName: string) => Promise<void> | void;
	}

	let { onAdd, onRemove }: Props = $props();

	// Collapsed by default. Reviewers who never touch the feature shouldn't
	// see a crowded sidebar on first load; those who do can expand it and
	// the state sticks for the session (no persistence across reloads —
	// this is a UX nicety, not data).
	let expanded = $state(false);
	let newName = $state('');
	let submitting = $state(false);

	const count = $derived(referenceNamesStore.count);

	async function handleAdd() {
		const trimmed = newName.trim();
		if (!trimmed || submitting) return;
		submitting = true;
		try {
			await onAdd(trimmed);
			newName = '';
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

	async function handleRemove(id: string, displayName: string) {
		if (submitting) return;
		submitting = true;
		try {
			await onRemove(id, displayName);
		} finally {
			submitting = false;
		}
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
		<UserCheck size={14} />
		<span class="flex-1">Publiek functionarissen</span>
		{#if count > 0}
			<sl-badge variant="neutral" pill>{count}</sl-badge>
		{/if}
	</button>

	{#if expanded}
		<div class="px-4 pb-3">
			<p class="mb-3 text-[11px] leading-relaxed text-neutral">
				Namen van personen die niet gelakt hoeven te worden (bijv. college B&amp;W).
				Geldt alleen voor dit document.
			</p>

			<div class="mb-2 flex items-center gap-2">
				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<sl-input
					size="small"
					placeholder="Bijv. Jan de Vries"
					value={newName}
					disabled={submitting}
					onsl-input={(e: Event) => {
						newName = (e.target as HTMLInputElement).value;
					}}
					onkeydown={handleKeydown}
					style="flex: 1; min-width: 0;"
				></sl-input>
				<sl-button
					size="small"
					variant="primary"
					disabled={submitting || !newName.trim()}
					onclick={handleAdd}
				>
					Toevoegen
				</sl-button>
			</div>

			{#if referenceNamesStore.error}
				<div class="mb-2 rounded border border-red-200 bg-red-50 px-2 py-1 text-[11px] text-red-700">
					{referenceNamesStore.error}
					<button
						type="button"
						class="ml-2 underline"
						onclick={() => referenceNamesStore.clearError()}
					>
						sluiten
					</button>
				</div>
			{/if}

			{#if referenceNamesStore.loading && count === 0}
				<div class="flex items-center gap-2 text-[11px] text-neutral">
					<sl-spinner style="font-size: 0.75rem;"></sl-spinner>
					Lijst laden...
				</div>
			{:else if count === 0}
				<div class="rounded border border-dashed border-gray-200 px-2 py-3 text-center text-[11px] text-neutral">
					Nog geen namen op de lijst.
				</div>
			{:else}
				<ul class="flex flex-col gap-1">
					{#each referenceNamesStore.names as name (name.id)}
						<li
							class="flex items-center gap-2 rounded border border-gray-200 bg-gray-50 px-2 py-1 text-xs"
						>
							<span class="flex-1 truncate" title={name.display_name}>
								{name.display_name}
							</span>
							<sl-tooltip content="Verwijder van lijst">
								<button
									type="button"
									class="rounded p-1 text-neutral hover:bg-red-100 hover:text-red-700 disabled:opacity-50"
									disabled={submitting}
									aria-label="Verwijder {name.display_name}"
									onclick={() => handleRemove(name.id, name.display_name)}
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
