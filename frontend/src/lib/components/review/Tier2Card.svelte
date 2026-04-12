<script lang="ts">
	import type { Detection, WooArticleCode } from '$lib/types';
	import { CONFIDENCE_LABELS, CONFIDENCE_COLORS } from '$lib/utils/confidence';
	import { confidenceToLevel } from '$lib/utils/tiers';
	import { WOO_ARTICLES, getArticleLabel } from '$lib/utils/woo-articles';

	interface Props {
		detection: Detection;
		onAccept: (id: string) => void;
		onReject: (id: string) => void;
		onPropagate: (id: string) => void;
	}

	let { detection, onAccept, onReject, onPropagate }: Props = $props();

	const isPending = $derived(detection.review_status === 'pending');
	const isAccepted = $derived(
		detection.review_status === 'accepted' || detection.review_status === 'auto_accepted'
	);
	const isRejected = $derived(detection.review_status === 'rejected');
	const isPropagated = $derived(!!detection.propagated_from);
	const article = $derived(detection.woo_article ? WOO_ARTICLES[detection.woo_article] : null);

	const confidenceLevel = $derived(confidenceToLevel(detection.confidence));
	const confidenceLabel = $derived(CONFIDENCE_LABELS[confidenceLevel]);
	const confidenceColor = $derived(CONFIDENCE_COLORS[confidenceLevel]);

	// Entity type badge colors
	const entityColors: Record<string, string> = {
		persoon: 'bg-primary/10 text-primary',
		adres: 'bg-purple-100 text-purple-700',
		datum: 'bg-gray-100 text-gray-600',
		organisatie: 'bg-blue-100 text-blue-600',
		gezondheid: 'bg-red-100 text-red-700'
	};
	const badgeClass = $derived(entityColors[detection.entity_type] ?? 'bg-gray-100 text-gray-600');
</script>

<div
	class="rounded-lg border p-3 transition-colors"
	class:border-warning={isPending}
	class:bg-amber-50={isPending}
	class:border-success={isAccepted}
	class:bg-green-50={isAccepted}
	class:border-gray-200={isRejected}
	class:bg-gray-50={isRejected}
>
	<!-- Header: entity type + article + confidence -->
	<div class="flex items-center gap-2 flex-wrap">
		<span class="inline-block rounded px-1.5 py-0.5 text-xs font-medium {badgeClass}">
			{detection.entity_type}
		</span>
		{#if article}
			<span class="rounded bg-primary/10 px-1.5 py-0.5 text-xs text-primary">
				{detection.woo_article}
			</span>
		{/if}
		<span
			class="ml-auto rounded px-1.5 py-0.5 text-xs"
			style="color: {confidenceColor}"
		>
			{confidenceLabel}
		</span>
	</div>

	<!-- Entity text with context -->
	<p class="mt-2 rounded bg-white p-2 font-mono text-sm leading-relaxed">
		<mark class="rounded bg-warning/30 px-0.5">{detection.entity_text}</mark>
	</p>

	<!-- Reasoning -->
	{#if detection.reasoning}
		<p class="mt-2 text-xs leading-relaxed text-neutral">
			{detection.reasoning}
		</p>
	{/if}

	<!-- Propagation note -->
	{#if isPropagated}
		<p class="mt-1 text-xs italic text-neutral">
			Gepropageerd vanuit eerder besluit
		</p>
	{/if}

	<!-- Action buttons -->
	{#if isPending}
		<div class="mt-3 flex items-center gap-2">
			<button
				class="flex-1 rounded bg-danger px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-danger/90"
				onclick={() => onAccept(detection.id)}
			>
				Lakken
			</button>
			<button
				class="flex-1 rounded border border-success px-3 py-1.5 text-sm font-medium text-success transition-colors hover:bg-success/10"
				onclick={() => onReject(detection.id)}
			>
				Niet lakken
			</button>
		</div>
	{:else if isAccepted}
		<div class="mt-3 flex items-center gap-2">
			<span class="flex-1 text-center text-xs text-danger font-medium">Gelakt</span>
			{#if detection.entity_type === 'persoon' && !isPropagated}
				<button
					class="rounded border border-primary px-2 py-1 text-xs text-primary hover:bg-primary/10"
					onclick={() => onPropagate(detection.id)}
				>
					Propageer naam
				</button>
			{/if}
		</div>
	{:else if isRejected}
		<p class="mt-3 text-center text-xs text-success font-medium">Zichtbaar gehouden</p>
	{/if}
</div>
