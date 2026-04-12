<script lang="ts">
	interface Props {
		tier1PendingCount: number;
		tier2HighConfidenceCount: number;
		onAcceptAllTier1: () => void;
		onAcceptHighConfidenceTier2: () => void;
	}

	let { tier1PendingCount, tier2HighConfidenceCount, onAcceptAllTier1, onAcceptHighConfidenceTier2 }: Props = $props();
</script>

<div class="flex flex-wrap gap-2">
	{#if tier1PendingCount > 0}
		<button
			class="rounded border border-gray-300 px-3 py-1.5 text-xs text-neutral transition-colors hover:border-primary hover:text-primary"
			onclick={onAcceptAllTier1}
		>
			Bevestig alle Trap 1 ({tier1PendingCount})
		</button>
	{/if}

	{#if tier2HighConfidenceCount > 0}
		<button
			class="rounded border border-gray-300 px-3 py-1.5 text-xs text-neutral transition-colors hover:border-primary hover:text-primary"
			onclick={onAcceptHighConfidenceTier2}
		>
			Bevestig hoog-vertrouwen Trap 2 ({tier2HighConfidenceCount})
		</button>
	{/if}
</div>
