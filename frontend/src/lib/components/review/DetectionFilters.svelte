<script lang="ts">
	import type { DetectionTier, ReviewStatus, EntityType } from '$lib/types';
	import { TIERS } from '$lib/utils/tiers';

	interface Props {
		currentTier: DetectionTier | null;
		currentStatus: ReviewStatus | null;
		currentEntityType: EntityType | null;
		onFilterChange: (key: 'tier' | 'status' | 'entityType' | 'page', value: unknown) => void;
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
		'persoon', 'bsn', 'email', 'telefoonnummer', 'adres', 'iban', 'postcode', 'kenteken'
	];
</script>

<div class="flex flex-wrap items-center gap-2 text-xs">
	<!-- Tier filter -->
	<div class="flex gap-1">
		{#each [1, 2, 3] as tier}
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
	<select
		class="rounded border border-gray-200 bg-white px-2 py-1 text-xs"
		value={currentStatus ?? ''}
		onchange={(e) =>
			onFilterChange('status', e.currentTarget.value || null)}
	>
		<option value="">Alle statussen</option>
		{#each statusOptions as opt}
			<option value={opt.value}>{opt.label}</option>
		{/each}
	</select>

	<!-- Entity type filter -->
	<select
		class="rounded border border-gray-200 bg-white px-2 py-1 text-xs"
		value={currentEntityType ?? ''}
		onchange={(e) =>
			onFilterChange('entityType', e.currentTarget.value || null)}
	>
		<option value="">Alle types</option>
		{#each entityOptions as etype}
			<option value={etype}>{etype}</option>
		{/each}
	</select>

	<!-- Clear -->
	{#if hasFilters}
		<button class="text-primary underline" onclick={onClear}>
			Wis filters
		</button>
	{/if}
</div>
