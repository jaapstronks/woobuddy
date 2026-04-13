<script lang="ts">
	import '@shoelace-style/shoelace/dist/components/button/button.js';

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

	// Group detections by tier. Area redactions (#07) are pulled out into
	// their own group — they can ride on any Woo article (so any tier) but
	// share a common "manually drawn rectangle, no text" shape that the
	// tier-specific cards can't render cleanly.
	const grouped = $derived.by(() => {
		const areas = detections.filter((d) => d.entity_type === 'area');
		const rest = detections.filter((d) => d.entity_type !== 'area');
		const tier1 = rest.filter((d) => d.tier === '1');
		const tier2 = rest.filter((d) => d.tier === '2');
		const tier3 = rest.filter((d) => d.tier === '3');
		return { areas, tier1, tier2, tier3 };
	});

	// Lowest page number that contains *any* bbox for a detection — used for
	// the "pagina N" label on area detections. Guards against the (rare)
	// case where bounding_boxes is empty.
	function areaPageLabel(det: typeof detections[number]): string {
		const pages = (det.bounding_boxes ?? []).map((b) => b.page);
		if (pages.length === 0) return '—';
		return String(Math.min(...pages) + 1);
	}

	// Scroll selected card into view
	$effect(() => {
		if (selectedId) {
			const el = document.querySelector(`[data-detection-id="${selectedId}"]`);
			el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
		}
	});
</script>

<div class="space-y-4 overflow-y-auto">
	<!-- Handmatige gebieden (#07) -->
	{#if grouped.areas.length > 0}
		<div>
			<h3 class="mb-2 flex items-center gap-2 text-xs font-semibold uppercase text-neutral">
				<span class="h-2 w-2 rounded-full bg-gray-900"></span>
				Handmatig gebied ({grouped.areas.length})
			</h3>
			<div class="space-y-1">
				{#each grouped.areas as det (det.id)}
					<button
						data-detection-id={det.id}
						class="w-full text-left"
						class:ring-2={det.id === selectedId}
						class:ring-primary={det.id === selectedId}
						class:rounded-lg={det.id === selectedId}
						onclick={() => onSelect(det.id)}
					>
						<div class="rounded-lg border border-gray-200 bg-gray-50 p-3 transition-colors hover:bg-gray-100">
							<div class="flex items-start justify-between gap-2">
								<div class="min-w-0 flex-1">
									<div class="flex items-center gap-2">
										<span class="inline-block rounded bg-gray-900 px-1.5 py-0.5 text-xs text-white">
											gebied
										</span>
										{#if det.woo_article}
											<span class="text-xs text-neutral">Art. {det.woo_article}</span>
										{/if}
									</div>
									<p class="mt-1 text-sm text-gray-700">
										Handmatig gebied — pagina {areaPageLabel(det)}
									</p>
								</div>
								<sl-button
									size="small"
									variant="default"
									onclick={(e: Event) => {
										e.stopPropagation();
										onReject(det.id);
									}}
								>
									Ontlakken
								</sl-button>
							</div>
						</div>
					</button>
				{/each}
			</div>
		</div>
	{/if}

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
