<script lang="ts">
	import '@shoelace-style/shoelace/dist/components/button/button.js';

	import type { Detection } from '$lib/types';
	import { WOO_ARTICLES } from '$lib/utils/woo-articles';

	interface Props {
		detection: Detection;
		onUnredact: (id: string) => void;
		/**
		 * Re-apply redaction after the reviewer pressed "Ontlakken". Tier 1
		 * doesn't need an article picker (the Tier 1 article is fixed at
		 * detection time), so we can flip the status straight back to
		 * accepted from the card.
		 */
		onRedact: (id: string) => void;
	}

	let { detection, onUnredact, onRedact }: Props = $props();

	const article = $derived(detection.woo_article ? WOO_ARTICLES[detection.woo_article] : null);
	const isRedacted = $derived(
		detection.review_status === 'auto_accepted' || detection.review_status === 'accepted'
	);
</script>

<div
	class="rounded-lg border p-3 transition-colors"
	class:border-gray-200={isRedacted}
	class:bg-gray-50={isRedacted}
	class:hover:bg-gray-100={isRedacted}
	class:border-success={!isRedacted}
	class:bg-green-50={!isRedacted}
	class:hover:bg-green-100={!isRedacted}
>
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
			{#if detection.entity_text}
				<p class="mt-1 truncate font-mono text-sm">{detection.entity_text}</p>
			{:else}
				<p class="mt-1 truncate font-mono text-xs italic text-neutral">
					— tekst niet beschikbaar —
				</p>
			{/if}
			<p class="mt-0.5 text-xs text-neutral">
				{isRedacted ? 'Auto-gelakt' : 'Zichtbaar gehouden'}
			</p>
		</div>

		{#if isRedacted}
			<sl-button
				size="small"
				variant="default"
				onclick={(e: Event) => {
					e.stopPropagation();
					onUnredact(detection.id);
				}}
			>
				Ontlakken
			</sl-button>
		{:else}
			<sl-button
				size="small"
				variant="default"
				onclick={(e: Event) => {
					e.stopPropagation();
					onRedact(detection.id);
				}}
			>
				Toch lakken
			</sl-button>
		{/if}
	</div>
</div>
