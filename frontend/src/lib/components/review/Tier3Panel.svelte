<script lang="ts">
	import '@shoelace-style/shoelace/dist/components/button/button.js';
	import '@shoelace-style/shoelace/dist/components/badge/badge.js';
	import '@shoelace-style/shoelace/dist/components/select/select.js';
	import '@shoelace-style/shoelace/dist/components/option/option.js';

	import type { Detection, WooArticleCode } from '$lib/types';
	import { WOO_ARTICLES, getArticleLabel, isRelativeGround } from '$lib/utils/woo-articles';
	import MotivationEditor from './MotivationEditor.svelte';
	import InterestWeighingChecklist from './InterestWeighingChecklist.svelte';
	import FactOpinionIndicator from './FactOpinionIndicator.svelte';

	interface Props {
		detection: Detection;
		motivationText?: string;
		onRedact: (id: string, article: WooArticleCode) => void;
		onKeep: (id: string) => void;
		onDefer: (id: string) => void;
		onReopen: (id: string) => void;
		onSaveMotivation?: (id: string, text: string) => void;
	}

	let { detection, motivationText = '', onRedact, onKeep, onDefer, onReopen, onSaveMotivation }: Props = $props();

	let selectedArticle = $state<WooArticleCode | null>(null);
	let showLegalText = $state(false);
	let weighingComplete = $state(false);

	// Reset local UI state when a different detection is shown
	$effect(() => {
		selectedArticle = detection.woo_article;
		showLegalText = false;
		weighingComplete = false;
	});

	const isPending = $derived(detection.review_status === 'pending' || detection.review_status === 'deferred');
	const isRedacted = $derived(
		detection.review_status === 'accepted' || detection.review_status === 'auto_accepted'
	);
	const needsWeighing = $derived(selectedArticle !== null && isRelativeGround(selectedArticle));
	const canRedact = $derived(selectedArticle !== null && (!needsWeighing || weighingComplete));

	// Parse reasoning for possible annotations
	const annotations = $derived.by(() => {
		if (!detection.reasoning) return [];
		return detection.reasoning
			.split('\n')
			.filter((line) => line.startsWith('['))
			.map((line) => {
				const match = line.match(/\[([^\]]+)\]\s*(.*?):\s*(.*)/);
				if (match) return { article: match[1], label: match[2], analysis: match[3] };
				return null;
			})
			.filter(Boolean) as { article: string; label: string; analysis: string }[];
	});

	// Parse sentence classifications
	const sentenceClassifications = $derived.by(() => {
		if (!detection.reasoning) return [];
		const lines = detection.reasoning.split('\n');
		const classIdx = lines.findIndex((l) => l.includes('Feit-mening classificatie'));
		if (classIdx === -1) return [];
		return lines
			.slice(classIdx + 1)
			.filter((l) => l.trim().startsWith('- ['))
			.map((line) => {
				const match = line.match(/\[(\w+)\]\s*(.*?)\.{3}\s*—\s*(.*)/);
				if (match) return { type: match[1], sentence: match[2], explanation: match[3] };
				return null;
			})
			.filter(Boolean) as { type: string; sentence: string; explanation: string }[];
	});

	const availableArticles = $derived(
		Object.values(WOO_ARTICLES).filter((a) => a.tier === '3')
	);
</script>

<div
	class="rounded-lg border p-4"
	class:border-primary={isPending}
	class:bg-blue-50={isPending}
	class:border-success={!isPending && !isRedacted}
	class:border-danger={isRedacted}
>
	<!-- Header -->
	<div class="mb-3 flex items-center justify-between">
		<span class="text-sm font-semibold text-primary">Inhoudelijke beoordeling</span>
		{#if detection.review_status === 'deferred'}
			<sl-badge variant="warning" pill>Uitgesteld</sl-badge>
		{/if}
	</div>

	<!-- Flagged passage -->
	<div class="mb-3 rounded bg-white p-3 text-sm leading-relaxed border border-gray-100">
		{detection.entity_text}
	</div>

	<!-- Environmental information warning (Art. 5.1 lid 6-7) -->
	{#if detection.is_environmental}
		<div class="mb-3 rounded border border-green-300 bg-green-50 p-2 text-xs text-green-800">
			<strong>Milieu-informatie (art. 5.1 lid 6-7 Woo):</strong> Deze passage bevat mogelijk
			milieu-informatie. Hiervoor gelden beperktere weigeringsmogelijkheden.
		</div>
	{/if}

	<!-- Annotations / possible grounds -->
	{#if annotations.length > 0}
		<div class="mb-3">
			<h4 class="mb-1 text-xs font-semibold uppercase text-neutral">Mogelijke gronden</h4>
			{#each annotations as ann}
				<div class="mb-1 rounded bg-white p-2 text-xs border border-gray-100">
					<span class="font-medium text-primary">{ann.article}</span>
					<span class="text-neutral"> — {ann.label}</span>
					<p class="mt-0.5 text-neutral">{ann.analysis}</p>
				</div>
			{/each}
		</div>
	{/if}

	<!-- Fact vs opinion (art. 5.2) -->
	{#if sentenceClassifications.length > 0}
		<div class="mb-3">
			<FactOpinionIndicator classifications={sentenceClassifications} />
		</div>
	{/if}

	<!-- Legal text (collapsible) -->
	{#if selectedArticle}
		<sl-button size="small" variant="text" class="mb-3" onclick={() => (showLegalText = !showLegalText)}>
			{showLegalText ? 'Verberg' : 'Toon'} wettekst
		</sl-button>
		{#if showLegalText}
			<div class="mb-3 rounded bg-gray-50 p-2 text-xs text-neutral">
				<strong>Art. {selectedArticle}</strong> —
				{WOO_ARTICLES[selectedArticle]?.description ?? ''}
			</div>
		{/if}
	{/if}

	<!-- Decision buttons -->
	{#if isPending}
		<div class="space-y-3">
			<!-- Article selection -->
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<!-- svelte-ignore a11y_label_has_associated_control -->
			<sl-select
				label="Weigeringsgrond"
				placeholder="Kies een grond..."
				value={selectedArticle ?? ''}
				onsl-change={(e: Event) => { selectedArticle = ((e.target as HTMLSelectElement).value || null) as WooArticleCode | null; }}
			>
				{#each availableArticles as art}
					<sl-option value={art.code}>{art.code} — {art.ground}</sl-option>
				{/each}
			</sl-select>

			<!-- Interest weighing checklist for relative grounds -->
			{#if selectedArticle && isRelativeGround(selectedArticle)}
				<InterestWeighingChecklist
					article={selectedArticle}
					onComplete={() => { weighingComplete = true; }}
				/>
			{/if}

			<!-- Motivation text editor -->
			{#if onSaveMotivation}
				<MotivationEditor
					detectionId={detection.id}
					initialText={motivationText}
					onSave={onSaveMotivation}
				/>
			{/if}

			<div class="flex gap-2">
				<sl-button
					variant="danger"
					class="flex-1"
					disabled={!canRedact}
					onclick={() => selectedArticle && onRedact(detection.id, selectedArticle)}
				>
					Lakken
				</sl-button>
				<sl-button
					variant="success"
					outline
					class="flex-1"
					onclick={() => onKeep(detection.id)}
				>
					Niet lakken
				</sl-button>
				<sl-button
					variant="default"
					onclick={() => onDefer(detection.id)}
				>
					Uitstellen
				</sl-button>
			</div>
		</div>
	{:else if isRedacted}
		<div class="flex items-center justify-between gap-2">
			<p class="text-sm font-medium text-danger">
				Gelakt op grond van art. {detection.woo_article}
			</p>
			<sl-button
				size="small"
				variant="default"
				onclick={(e: Event) => {
					e.stopPropagation();
					onKeep(detection.id);
				}}
			>
				Ontlakken
			</sl-button>
		</div>
	{:else}
		<div class="flex items-center justify-between gap-2">
			<p class="text-sm font-medium text-success">Niet gelakt</p>
			<sl-button
				size="small"
				variant="default"
				onclick={(e: Event) => {
					e.stopPropagation();
					onReopen(detection.id);
				}}
			>
				Opnieuw beoordelen
			</sl-button>
		</div>
	{/if}
</div>
