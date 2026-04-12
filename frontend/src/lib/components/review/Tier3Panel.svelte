<script lang="ts">
	import type { Detection, WooArticleCode } from '$lib/types';
	import { WOO_ARTICLES, getArticleLabel, isRelativeGround } from '$lib/utils/woo-articles';

	interface Props {
		detection: Detection;
		onRedact: (id: string, article: WooArticleCode) => void;
		onKeep: (id: string) => void;
		onDefer: (id: string) => void;
	}

	let { detection, onRedact, onKeep, onDefer }: Props = $props();

	let selectedArticle = $state<WooArticleCode | null>(detection.woo_article);
	let showLegalText = $state(false);

	const isPending = $derived(detection.review_status === 'pending' || detection.review_status === 'deferred');
	const isRedacted = $derived(
		detection.review_status === 'accepted' || detection.review_status === 'auto_accepted'
	);

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
		Object.values(WOO_ARTICLES).filter((a) => a.tier === 3)
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
			<span class="rounded bg-warning/20 px-2 py-0.5 text-xs text-warning">Uitgesteld</span>
		{/if}
	</div>

	<!-- Flagged passage -->
	<div class="mb-3 rounded bg-white p-3 text-sm leading-relaxed border border-gray-100">
		{detection.entity_text}
	</div>

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
			<h4 class="mb-1 text-xs font-semibold uppercase text-neutral">Feit-mening analyse</h4>
			{#each sentenceClassifications as sc}
				<div class="mb-1 flex items-start gap-2 text-xs">
					<span
						class="mt-0.5 shrink-0 rounded px-1.5 py-0.5 font-medium"
						class:bg-blue-100={sc.type === 'fact'}
						class:text-blue-700={sc.type === 'fact'}
						class:bg-amber-100={sc.type === 'opinion'}
						class:text-warning={sc.type === 'opinion'}
						class:bg-purple-100={sc.type === 'mixed'}
						class:text-purple-700={sc.type === 'mixed'}
						class:bg-gray-100={sc.type !== 'fact' && sc.type !== 'opinion' && sc.type !== 'mixed'}
					>
						{sc.type}
					</span>
					<div>
						<p class="text-gray-700">{sc.sentence}...</p>
						<p class="text-neutral">{sc.explanation}</p>
					</div>
				</div>
			{/each}
		</div>
	{/if}

	<!-- Legal text (collapsible) -->
	{#if selectedArticle}
		<button
			class="mb-3 text-xs text-primary underline"
			onclick={() => (showLegalText = !showLegalText)}
		>
			{showLegalText ? 'Verberg' : 'Toon'} wettekst
		</button>
		{#if showLegalText}
			<div class="mb-3 rounded bg-gray-50 p-2 text-xs text-neutral">
				<strong>Art. {selectedArticle}</strong> —
				{WOO_ARTICLES[selectedArticle]?.description ?? ''}
			</div>
		{/if}
	{/if}

	<!-- Decision buttons -->
	{#if isPending}
		<div class="space-y-2">
			<!-- Article selection -->
			<div>
				<label class="block text-xs font-medium text-neutral mb-1">Weigeringsgrond</label>
				<select
					bind:value={selectedArticle}
					class="w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
				>
					<option value={null}>Kies een grond...</option>
					{#each availableArticles as art}
						<option value={art.code}>{art.code} — {art.ground}</option>
					{/each}
				</select>
			</div>

			<!-- Interest weighing reminder for relative grounds -->
			{#if selectedArticle && isRelativeGround(selectedArticle)}
				<div class="rounded border border-warning/30 bg-warning/10 p-2 text-xs text-warning">
					Let op: bij relatieve gronden is een belangenafweging vereist.
				</div>
			{/if}

			<div class="flex gap-2">
				<button
					class="flex-1 rounded bg-danger px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
					disabled={!selectedArticle}
					onclick={() => selectedArticle && onRedact(detection.id, selectedArticle)}
				>
					Lakken
				</button>
				<button
					class="flex-1 rounded border border-success px-3 py-2 text-sm font-medium text-success hover:bg-success/10"
					onclick={() => onKeep(detection.id)}
				>
					Niet lakken
				</button>
				<button
					class="rounded border border-neutral px-3 py-2 text-sm text-neutral hover:bg-gray-100"
					onclick={() => onDefer(detection.id)}
				>
					Uitstellen
				</button>
			</div>
		</div>
	{:else if isRedacted}
		<p class="text-center text-sm font-medium text-danger">
			Gelakt op grond van art. {detection.woo_article}
		</p>
	{:else}
		<p class="text-center text-sm font-medium text-success">Niet gelakt</p>
	{/if}
</div>
