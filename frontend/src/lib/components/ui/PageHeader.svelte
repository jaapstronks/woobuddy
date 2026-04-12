<script lang="ts">
	import { ArrowLeft } from 'lucide-svelte';

	interface Props {
		title: string;
		subtitle?: string;
		backHref?: string;
		backLabel?: string;
	}

	let { title, subtitle, backHref, backLabel = 'Terug' }: Props = $props();
</script>

{#if backHref}
	<a href={backHref} class="back-link">
		<ArrowLeft size={16} />
		{backLabel}
	</a>
{/if}

<div class="page-header">
	<h1 class="page-header__title">{title}</h1>
	{#if subtitle}
		<p class="page-header__subtitle">{subtitle}</p>
	{/if}
</div>

<style>
	.back-link {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		font-size: 0.875rem;
		color: var(--color-neutral);
		text-decoration: none;
		margin-bottom: 1rem;
	}

	.back-link:hover {
		color: var(--color-primary);
	}

	.page-header {
		margin-bottom: 1.5rem;
	}

	.page-header__title {
		font-size: 1.5rem;
		font-weight: 700;
		color: #111827;
	}

	.page-header__subtitle {
		margin-top: 0.25rem;
		font-size: 0.875rem;
		color: var(--color-neutral);
	}
</style>
