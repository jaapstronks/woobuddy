<script lang="ts">
	import type { Detection } from '$lib/types';

	interface Props {
		/** Detections that were propagated from a source decision */
		propagatedDetections: Detection[];
		onUndoPropagate: (sourceId: string) => void;
	}

	let { propagatedDetections, onUndoPropagate }: Props = $props();

	// Group by source detection
	const grouped = $derived.by(() => {
		const groups = new Map<string, Detection[]>();
		for (const det of propagatedDetections) {
			if (!det.propagated_from) continue;
			const existing = groups.get(det.propagated_from) ?? [];
			existing.push(det);
			groups.set(det.propagated_from, existing);
		}
		return groups;
	});
</script>

{#if grouped.size > 0}
	<div class="rounded-lg border border-primary/20 bg-primary/5 p-3">
		<h4 class="mb-2 text-xs font-semibold uppercase text-primary">Gepropageerde beslissingen</h4>
		{#each [...grouped.entries()] as [sourceId, dets]}
			<div class="mb-2 flex items-center justify-between text-xs last:mb-0">
				<div>
					<span class="font-medium">"{dets[0]?.entity_text}"</span>
					<span class="text-neutral">
						&mdash; {dets.length} {dets.length === 1 ? 'keer' : 'keer'} gepropageerd
					</span>
				</div>
				<button
					class="rounded border border-primary/30 px-2 py-0.5 text-primary hover:bg-primary/10"
					onclick={() => onUndoPropagate(sourceId)}
				>
					Ongedaan maken
				</button>
			</div>
		{/each}
	</div>
{/if}
