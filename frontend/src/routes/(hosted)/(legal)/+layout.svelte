<script lang="ts">
	import Header from '$lib/components/landing/Header.svelte';
	import Footer from '$lib/components/landing/Footer.svelte';

	let { children } = $props();
</script>

<div class="min-h-screen bg-bg text-ink">
	<Header />
	<main class="px-6 pt-28 pb-16 sm:pt-32 sm:pb-20">
		<article class="mx-auto max-w-3xl legal-prose">
			{@render children()}
		</article>
	</main>
	<Footer />
</div>

<style>
	.legal-prose :global(h1) {
		font-family: var(--font-serif);
		font-size: 2.5rem;
		line-height: 1.1;
		letter-spacing: -0.01em;
		color: var(--color-ink);
		margin-bottom: 0.5rem;
	}

	.legal-prose :global(.lead) {
		color: var(--color-ink-soft);
		font-size: 1.05rem;
		line-height: 1.6;
		margin-bottom: 2.5rem;
	}

	.legal-prose :global(h2) {
		font-family: var(--font-serif);
		font-size: 1.5rem;
		line-height: 1.25;
		color: var(--color-ink);
		margin-top: 2.5rem;
		margin-bottom: 0.75rem;
	}

	.legal-prose :global(h3) {
		font-size: 1.05rem;
		font-weight: 600;
		color: var(--color-ink);
		margin-top: 1.5rem;
		margin-bottom: 0.5rem;
	}

	.legal-prose :global(p),
	.legal-prose :global(li) {
		color: var(--color-ink-soft);
		line-height: 1.7;
	}

	.legal-prose :global(p) {
		margin-bottom: 1rem;
	}

	.legal-prose :global(ul),
	.legal-prose :global(ol) {
		margin-bottom: 1rem;
		padding-left: 1.25rem;
	}

	.legal-prose :global(ul) {
		list-style-type: disc;
	}

	.legal-prose :global(ol) {
		list-style-type: decimal;
	}

	.legal-prose :global(li) {
		margin-bottom: 0.35rem;
	}

	.legal-prose :global(a) {
		color: var(--color-primary);
		text-decoration: underline;
		text-underline-offset: 2px;
	}

	.legal-prose :global(a:hover) {
		color: var(--color-primary-hover);
	}

	.legal-prose :global(strong) {
		color: var(--color-ink);
		font-weight: 600;
	}

	.legal-prose :global(.meta) {
		font-size: 0.85rem;
		color: var(--color-ink-mute);
		margin-bottom: 2.5rem;
	}

	.legal-prose :global(.callout) {
		border-left: 3px solid var(--color-primary);
		background: var(--color-primary-soft);
		padding: 1rem 1.25rem;
		border-radius: 4px;
		margin: 1.5rem 0 2rem;
	}

	.legal-prose :global(.callout p:last-child) {
		margin-bottom: 0;
	}
</style>
