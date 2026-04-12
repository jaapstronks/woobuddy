<script lang="ts">
	import '@shoelace-style/shoelace/dist/components/button/button.js';

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
		<sl-button size="small" variant="default" onclick={onAcceptAllTier1}>
			Bevestig alle Trap 1 ({tier1PendingCount})
		</sl-button>
	{/if}

	{#if tier2HighConfidenceCount > 0}
		<sl-button size="small" variant="default" onclick={onAcceptHighConfidenceTier2}>
			Bevestig hoog-vertrouwen Trap 2 ({tier2HighConfidenceCount})
		</sl-button>
	{/if}
</div>
