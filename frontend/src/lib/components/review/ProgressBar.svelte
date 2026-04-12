<script lang="ts">
	import '@shoelace-style/shoelace/dist/components/progress-bar/progress-bar.js';

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
		1: '#4b5563',
		2: 'var(--color-warning)',
		3: 'var(--color-primary)'
	};
</script>

<div class="flex items-center gap-4 text-xs">
	{#each tiers as tp}
		{@const pct = tp.total > 0 ? Math.round((tp.reviewed / tp.total) * 100) : 100}
		{@const done = tp.reviewed === tp.total}
		<div class="flex items-center gap-2">
			<span class="font-medium text-neutral">{tierLabels[tp.tier]}:</span>
			<sl-progress-bar
				value={pct}
				style="--height: 6px; --indicator-color: {tierColors[tp.tier]}; width: 4rem;"
			></sl-progress-bar>
			<span class:text-success={done} class:font-medium={done}>
				{tp.reviewed}/{tp.total}
				{#if done}&#10003;{/if}
			</span>
		</div>
	{/each}
</div>
