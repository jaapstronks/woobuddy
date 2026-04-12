<script lang="ts">
	import type { Detection, WooArticleCode } from '$lib/types';
	import Tier1Card from './Tier1Card.svelte';
	import Tier2Card from './Tier2Card.svelte';
	import Tier3Panel from './Tier3Panel.svelte';

	interface Props {
		detections: Detection[];
		selectedId: string | null;
		onSelect: (id: string) => void;
		onAccept: (id: string) => void;
		onReject: (id: string) => void;
		onDefer: (id: string) => void;
		onRedactWithArticle: (id: string, article: WooArticleCode) => void;
		onSaveMotivation?: (id: string, text: string) => void;
	}

	let {
		detections,
		selectedId,
		onSelect,
		onAccept,
		onReject,
		onDefer,
		onRedactWithArticle,
		onSaveMotivation
	}: Props = $props();

	// Group detections by tier
	const grouped = $derived.by(() => {
		const tier1 = detections.filter((d) => d.tier === '1');
		const tier2 = detections.filter((d) => d.tier === '2');
		const tier3 = detections.filter((d) => d.tier === '3');
		return { tier1, tier2, tier3 };
	});

	// Scroll selected card into view
	$effect(() => {
		if (selectedId) {
			const el = document.querySelector(`[data-detection-id="${selectedId}"]`);
			el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
		}
	});
</script>

<div class="space-y-4 overflow-y-auto">
	<!-- Tier 1 -->
	{#if grouped.tier1.length > 0}
		<div>
			<h3 class="mb-2 flex items-center gap-2 text-xs font-semibold uppercase text-neutral">
				<span class="h-2 w-2 rounded-full bg-gray-700"></span>
				Trap 1 — Auto-gelakt ({grouped.tier1.length})
			</h3>
			<div class="space-y-1">
				{#each grouped.tier1 as det (det.id)}
					<button
						data-detection-id={det.id}
						class="w-full text-left"
						class:ring-2={det.id === selectedId}
						class:ring-primary={det.id === selectedId}
						class:rounded-lg={det.id === selectedId}
						onclick={() => onSelect(det.id)}
					>
						<Tier1Card detection={det} onUnredact={onReject} />
					</button>
				{/each}
			</div>
		</div>
	{/if}

	<!-- Tier 2 -->
	{#if grouped.tier2.length > 0}
		<div>
			<h3 class="mb-2 flex items-center gap-2 text-xs font-semibold uppercase text-neutral">
				<span class="h-2 w-2 rounded-full bg-warning"></span>
				Trap 2 — Beoordelen ({grouped.tier2.length})
			</h3>
			<div class="space-y-2">
				{#each grouped.tier2 as det (det.id)}
					<button
						data-detection-id={det.id}
						class="w-full text-left"
						class:ring-2={det.id === selectedId}
						class:ring-primary={det.id === selectedId}
						class:rounded-lg={det.id === selectedId}
						onclick={() => onSelect(det.id)}
					>
						<Tier2Card
							detection={det}
							{onAccept}
							{onReject}
						/>
					</button>
				{/each}
			</div>
		</div>
	{/if}

	<!-- Tier 3 -->
	{#if grouped.tier3.length > 0}
		<div>
			<h3 class="mb-2 flex items-center gap-2 text-xs font-semibold uppercase text-neutral">
				<span class="h-2 w-2 rounded-full bg-primary"></span>
				Trap 3 — Analyse ({grouped.tier3.length})
			</h3>
			<div class="space-y-3">
				{#each grouped.tier3 as det (det.id)}
					<button
						data-detection-id={det.id}
						class="w-full text-left"
						class:ring-2={det.id === selectedId}
						class:ring-primary={det.id === selectedId}
						class:rounded-lg={det.id === selectedId}
						onclick={() => onSelect(det.id)}
					>
						<Tier3Panel
							detection={det}
							onRedact={onRedactWithArticle}
							onKeep={onReject}
							{onDefer}
							{onSaveMotivation}
						/>
					</button>
				{/each}
			</div>
		</div>
	{/if}

	{#if detections.length === 0}
		<div class="flex h-32 items-center justify-center text-sm text-neutral">
			Geen detecties gevonden
		</div>
	{/if}
</div>
