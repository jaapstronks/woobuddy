<script lang="ts">
	import '@shoelace-style/shoelace/dist/components/button/button.js';

	import type { Detection } from '$lib/types';
	import { WOO_ARTICLES } from '$lib/utils/woo-articles';

	interface Props {
		detection: Detection;
		onUnredact: (id: string) => void;
	}

	let { detection, onUnredact }: Props = $props();

	const article = $derived(detection.woo_article ? WOO_ARTICLES[detection.woo_article] : null);
	const isRedacted = $derived(
		detection.review_status === 'auto_accepted' || detection.review_status === 'accepted'
	);
</script>

<div class="rounded-lg border border-gray-200 bg-gray-50 p-3 transition-colors hover:bg-gray-100">
	<div class="flex items-start justify-between gap-2">
		<div class="min-w-0 flex-1">
			<div class="flex items-center gap-2">
				<span class="inline-block rounded bg-gray-700 px-1.5 py-0.5 text-xs text-white">
					{detection.entity_type}
				</span>
				{#if article}
					<span class="text-xs text-neutral">Art. {detection.woo_article}</span>
				{/if}
			</div>
			<p class="mt-1 truncate font-mono text-sm">{detection.entity_text}</p>
			<p class="mt-0.5 text-xs text-neutral">
				{isRedacted ? 'Auto-gelakt' : 'Ontlakt'}
			</p>
		</div>

		{#if isRedacted}
			<sl-button size="small" variant="default" onclick={() => onUnredact(detection.id)}>
				Ontlakken
			</sl-button>
		{:else}
			<span class="shrink-0 rounded bg-success/10 px-2 py-1 text-xs text-success">
				Zichtbaar
			</span>
		{/if}
	</div>
</div>
