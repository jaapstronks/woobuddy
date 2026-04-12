<script lang="ts">
	import type { DetectionTier } from '$lib/types';

	interface TierProgress {
		tier: DetectionTier;
		reviewed: number;
		total: number;
	}

	interface Props {
		tiers: TierProgress[];
	}

	let { tiers }: Props = $props();

	const tierLabels: Record<DetectionTier, string> = {
		1: 'Trap 1',
		2: 'Trap 2',
		3: 'Trap 3'
	};

	const tierColors: Record<DetectionTier, string> = {
		1: 'bg-gray-600',
		2: 'bg-warning',
		3: 'bg-primary'
	};
</script>

<div class="flex items-center gap-4 text-xs">
	{#each tiers as tp}
		{@const pct = tp.total > 0 ? Math.round((tp.reviewed / tp.total) * 100) : 100}
		{@const done = tp.reviewed === tp.total}
		<div class="flex items-center gap-2">
			<span class="font-medium text-neutral">{tierLabels[tp.tier]}:</span>
			<div class="h-1.5 w-16 overflow-hidden rounded-full bg-gray-200">
				<div
					class="h-full rounded-full transition-all {tierColors[tp.tier]}"
					style="width: {pct}%"
				></div>
			</div>
			<span class:text-success={done} class:font-medium={done}>
				{tp.reviewed}/{tp.total}
				{#if done}&#10003;{/if}
			</span>
		</div>
	{/each}
</div>
