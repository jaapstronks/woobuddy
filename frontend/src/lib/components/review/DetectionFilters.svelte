<script lang="ts">
	import '@shoelace-style/shoelace/dist/components/select/select.js';
	import '@shoelace-style/shoelace/dist/components/option/option.js';
	import '@shoelace-style/shoelace/dist/components/button/button.js';

	import type { DetectionTier, ReviewStatus, EntityType } from '$lib/types';
	import { TIERS } from '$lib/utils/tiers';

	interface Props {
		currentTier: DetectionTier | null;
		currentStatus: ReviewStatus | null;
		currentEntityType: EntityType | null;
		onFilterChange: (key: 'tier' | 'status' | 'entityType', value: unknown) => void;
		onClear: () => void;
	}

	let { currentTier, currentStatus, currentEntityType, onFilterChange, onClear }: Props = $props();

	const hasFilters = $derived(
		currentTier !== null || currentStatus !== null || currentEntityType !== null
	);

	const statusOptions: { value: ReviewStatus; label: string }[] = [
		{ value: 'pending', label: 'Te beoordelen' },
		{ value: 'auto_accepted', label: 'Auto-gelakt' },
		{ value: 'accepted', label: 'Geaccepteerd' },
		{ value: 'rejected', label: 'Afgewezen' },
		{ value: 'deferred', label: 'Uitgesteld' }
	];

	const entityOptions: EntityType[] = [
		'persoon', 'bsn', 'email', 'telefoon', 'adres', 'iban', 'postcode', 'kenteken'
	];
</script>

<div class="flex flex-wrap items-center gap-2 text-xs">
	<!-- Tier filter -->
	<div class="flex gap-1">
		{#each ['1', '2', '3'] as const as tier}
			<button
				class="rounded px-2 py-1 transition-colors"
				class:bg-primary={currentTier === tier}
				class:text-white={currentTier === tier}
				class:bg-gray-100={currentTier !== tier}
				class:text-neutral={currentTier !== tier}
				onclick={() => onFilterChange('tier', currentTier === tier ? null : tier)}
			>
				Trap {tier}
			</button>
		{/each}
	</div>

	<span class="text-gray-300">|</span>

	<!-- Status filter -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<sl-select
		size="small"
		placeholder="Alle statussen"
		value={currentStatus ?? ''}
		clearable
		onsl-change={(e: Event) => onFilterChange('status', (e.target as HTMLSelectElement).value || null)}
	>
		{#each statusOptions as opt}
			<sl-option value={opt.value}>{opt.label}</sl-option>
		{/each}
	</sl-select>

	<!-- Entity type filter -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<sl-select
		size="small"
		placeholder="Alle types"
		value={currentEntityType ?? ''}
		clearable
		onsl-change={(e: Event) => onFilterChange('entityType', (e.target as HTMLSelectElement).value || null)}
	>
		{#each entityOptions as etype}
			<sl-option value={etype}>{etype}</sl-option>
		{/each}
	</sl-select>

	<!-- Clear -->
	{#if hasFilters}
		<sl-button size="small" variant="text" onclick={onClear}>
			Wis filters
		</sl-button>
	{/if}
</div>
