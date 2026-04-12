<script lang="ts">
	import type { DossierWithStats, DetectionTier } from '$lib/types';
	import { TIERS } from '$lib/utils/tiers';

	interface Props {
		stats: DossierWithStats['detection_counts'];
		documentCount: number;
	}

	let { stats, documentCount }: Props = $props();

	const tierList: DetectionTier[] = [1, 2, 3];

	function getTierColor(tier: DetectionTier): string {
		return TIERS[tier].color;
	}

	function getTierCount(tier: DetectionTier): number {
		return stats.by_tier[tier] ?? 0;
	}
</script>

<div class="space-y-4">
	<div class="grid grid-cols-2 gap-3">
		<div class="rounded-lg border border-gray-200 bg-white p-3 text-center">
			<p class="text-2xl font-bold text-gray-900">{documentCount}</p>
			<p class="text-xs text-neutral">Documenten</p>
		</div>
		<div class="rounded-lg border border-gray-200 bg-white p-3 text-center">
			<p class="text-2xl font-bold text-gray-900">{stats.total}</p>
			<p class="text-xs text-neutral">Detecties</p>
		</div>
	</div>

	<!-- By tier -->
	{#if stats.total > 0}
		<div>
			<h4 class="mb-2 text-xs font-semibold uppercase text-neutral">Per trap</h4>
			<div class="space-y-1">
				{#each tierList as tier (tier)}
					{@const count = getTierCount(tier)}
					{@const pct = stats.total > 0 ? Math.round((count / stats.total) * 100) : 0}
					<div class="flex items-center gap-2 text-xs">
						<span class="w-14 text-neutral">Trap {tier}</span>
						<div class="h-2 flex-1 overflow-hidden rounded-full bg-gray-100">
							<div
								class="h-full rounded-full"
								style="width: {pct}%; background: {getTierColor(tier)}"
							></div>
						</div>
						<span class="w-8 text-right font-medium">{count}</span>
					</div>
				{/each}
			</div>
		</div>

		<!-- By status -->
		<div>
			<h4 class="mb-2 text-xs font-semibold uppercase text-neutral">Per status</h4>
			<div class="grid grid-cols-2 gap-2 text-xs">
				{#each Object.entries(stats.by_status) as [status, count]}
					<div class="flex justify-between rounded bg-gray-50 px-2 py-1">
						<span class="text-neutral">{status}</span>
						<span class="font-medium">{count}</span>
					</div>
				{/each}
			</div>
		</div>
	{/if}
</div>
