<script lang="ts">
	import '@shoelace-style/shoelace/dist/components/button/button.js';
	import '@shoelace-style/shoelace/dist/components/checkbox/checkbox.js';

	import type { WooArticleCode } from '$lib/types';
	import { WOO_ARTICLES, isRelativeGround } from '$lib/utils/woo-articles';

	interface Props {
		article: WooArticleCode;
		onComplete: (outcome: Record<string, boolean>) => void;
	}

	let { article, onComplete }: Props = $props();

	const articleInfo = $derived(WOO_ARTICLES[article]);
	const isRelative = $derived(isRelativeGround(article));

	// Standard interest-weighing checklist items for relative grounds
	const checklistItems = [
		{
			key: 'identified_interest',
			label: 'Het belang dat met geheimhouding wordt gediend is geïdentificeerd',
			required: true
		},
		{
			key: 'weighed_disclosure',
			label: 'Het belang van openbaarmaking is meegewogen',
			required: true
		},
		{
			key: 'proportional',
			label: 'De weigering is proportioneel (niet meer gelakt dan nodig)',
			required: true
		},
		{
			key: 'no_partial',
			label: 'Gecontroleerd of gedeeltelijke openbaarmaking mogelijk is',
			required: false
		},
		{
			key: 'documented',
			label: 'De afweging is gedocumenteerd in de motiveringstekst',
			required: true
		}
	];

	let checked = $state<Record<string, boolean>>(
		Object.fromEntries(checklistItems.map((item) => [item.key, false]))
	);

	const allRequiredChecked = $derived(
		checklistItems.filter((i) => i.required).every((i) => checked[i.key])
	);

	function handleComplete() {
		onComplete(checked);
	}
</script>

{#if isRelative}
	<div class="rounded-lg border border-warning/30 bg-warning/5 p-3">
		<h4 class="mb-2 text-xs font-semibold uppercase text-warning">
			Belangenafweging (art. {article})
		</h4>
		<p class="mb-3 text-xs text-neutral">
			Bij relatieve gronden is een belangenafweging vereist. Controleer onderstaande punten.
		</p>

		<div class="space-y-2">
			{#each checklistItems as item}
				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<sl-checkbox
					checked={checked[item.key] || undefined}
					onsl-change={(e: Event) => { checked[item.key] = (e.target as HTMLInputElement).checked; }}
					class="text-xs"
				>
					{item.label}
					{#if item.required}
						<span class="text-danger">*</span>
					{/if}
				</sl-checkbox>
			{/each}
		</div>

		{#if allRequiredChecked}
			<sl-button variant="primary" class="mt-3" style="width: 100%;" onclick={handleComplete}>
				Belangenafweging afgerond
			</sl-button>
		{:else}
			<p class="mt-2 text-xs italic text-warning">
				Alle verplichte punten (*) moeten zijn aangevinkt
			</p>
		{/if}
	</div>
{/if}
