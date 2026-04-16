<script lang="ts">
	import '@shoelace-style/shoelace/dist/components/select/select.js';
	import '@shoelace-style/shoelace/dist/components/option/option.js';
	import '@shoelace-style/shoelace/dist/components/textarea/textarea.js';
	import '@shoelace-style/shoelace/dist/components/divider/divider.js';

	import type { EntityType, WooArticleCode, DetectionTier } from '$lib/types';
	import { WOO_ARTICLES, ARTICLE_TO_ENTITY, ARTICLES_BY_TIER } from '$lib/utils/woo-articles';
	import { ENTITY_FORM_LABELS } from '$lib/utils/entity-types';
	import { getRecentArticles } from '$lib/services/recent-articles';

	interface Props {
		article: WooArticleCode | '';
		entityType: EntityType;
		motivation: string;
		/**
		 * When set, the article→entityType auto-nudge is suppressed until
		 * the reviewer explicitly picks a different type. Used by area
		 * flows where the initial type is `'area'` and shouldn't be
		 * overwritten by the article's implied type.
		 */
		suppressInitialNudge?: boolean;
	}

	let {
		article = $bindable(),
		entityType = $bindable(),
		motivation = $bindable(),
		suppressInitialNudge = false
	}: Props = $props();

	const recentCodes = $state(getRecentArticles());
	// svelte-ignore state_referenced_locally
	let userTouchedType = $state(suppressInitialNudge);

	// Pre-fill the motivation template whenever the article changes.
	$effect(() => {
		if (!article) return;
		const info = WOO_ARTICLES[article as WooArticleCode];
		if (info) motivation = `Informatie valt onder Art. ${info.code} Woo — ${info.ground}.`;
	});

	// When article changes, nudge the entity type if the new article
	// implies a different one — unless the reviewer has manually
	// overridden it.
	$effect(() => {
		if (!article || userTouchedType) return;
		const implied = ARTICLE_TO_ENTITY[article as WooArticleCode];
		if (implied) entityType = implied;
	});
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<!-- svelte-ignore a11y_label_has_associated_control -->
<sl-select
	label="Woo-grond"
	size="small"
	value={article}
	onsl-change={(e: Event) => {
		article = ((e.target as HTMLSelectElement).value || '') as WooArticleCode | '';
		userTouchedType = false;
	}}
>
	{#if recentCodes.length > 0}
		<small slot="label-suffix">&nbsp;</small>
		<sl-option disabled>— Recent gebruikt —</sl-option>
		{#each recentCodes as code}
			{#if WOO_ARTICLES[code]}
				<sl-option value={code}>
					Tier {WOO_ARTICLES[code].tier} · {code} — {WOO_ARTICLES[code].ground}
				</sl-option>
			{/if}
		{/each}
		<sl-divider></sl-divider>
	{/if}
	<sl-option disabled>— Tier 1 (harde identifiers) —</sl-option>
	{#each ARTICLES_BY_TIER['1'] as art}
		<sl-option value={art.code}>{art.code} — {art.ground}</sl-option>
	{/each}
	<sl-option disabled>— Tier 2 (persoonsgegevens) —</sl-option>
	{#each ARTICLES_BY_TIER['2'] as art}
		<sl-option value={art.code}>{art.code} — {art.ground}</sl-option>
	{/each}
	<sl-option disabled>— Tier 3 (inhoudelijk) —</sl-option>
	{#each ARTICLES_BY_TIER['3'] as art}
		<sl-option value={art.code}>{art.code} — {art.ground}</sl-option>
	{/each}
</sl-select>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<!-- svelte-ignore a11y_label_has_associated_control -->
<sl-select
	label="Type"
	size="small"
	value={entityType}
	onsl-change={(e: Event) => {
		entityType = (e.target as HTMLSelectElement).value as EntityType;
		userTouchedType = true;
	}}
>
	{#each Object.entries(ENTITY_FORM_LABELS) as [value, label]}
		<sl-option value={value}>{label}</sl-option>
	{/each}
</sl-select>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<!-- svelte-ignore a11y_label_has_associated_control -->
<sl-textarea
	label="Motivering"
	size="small"
	rows="2"
	value={motivation}
	onsl-input={(e: Event) => { motivation = (e.target as HTMLTextAreaElement).value; }}
></sl-textarea>
