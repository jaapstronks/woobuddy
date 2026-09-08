<script lang="ts">
	import Header from '$lib/components/landing/Header.svelte';
	import Footer from '$lib/components/landing/Footer.svelte';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();
</script>

<svelte:head>
	<title>Changelog — WOO Buddy</title>
	<meta
		name="description"
		content="Wat er in elke versie van WOO Buddy is veranderd, geschreven voor de beoordelaar die ermee werkt. Per versie een korte Nederlandse toelichting."
	/>
	<link rel="canonical" href="https://woobuddy.nl/changelog" />
	<meta property="og:url" content="https://woobuddy.nl/changelog" />
	<meta property="og:title" content="Changelog — WOO Buddy" />
	<meta property="og:type" content="article" />
</svelte:head>

<div class="min-h-screen bg-bg text-ink">
	<Header />
	<main class="px-6 pt-28 pb-16 sm:pt-32 sm:pb-20">
		<article class="mx-auto max-w-3xl changelog-prose">
			<h1>Changelog</h1>
			<p class="lead">
				Wat er in elke versie is veranderd, geschreven voor wie ermee werkt. De technische
				versie, per commit en in het Engels, staat in de
				<a
					href="https://github.com/jaapstronks/woobuddy/blob/main/CHANGELOG.md"
					target="_blank"
					rel="noopener noreferrer">CHANGELOG.md</a
				>
				in de repository; hoe de versienummers werken staat in het
				<a
					href="https://github.com/jaapstronks/woobuddy/blob/main/docs/reference/versioning.md"
					target="_blank"
					rel="noopener noreferrer">versiebeleid</a
				>.
			</p>

			<ol class="timeline">
				{#each data.notes as note (note.version)}
					<li id={note.version} class="entry">
						<div class="entry-head">
							<h2>
								<a href="#{note.version}" class="anchor">v{note.version}</a>
								{#if note.latest}
									<span class="badge">nieuwste</span>
								{/if}
							</h2>
							<p class="meta">
								<time datetime={note.date}>{note.dateLabel}</time>
							</p>
						</div>
						<p class="summary">{note.summary}</p>
						<!-- Hand-written notes from src/content/releases, rendered at
						     build time. No user input reaches this. -->
						{@html note.html}
					</li>
				{/each}
			</ol>
		</article>
	</main>
	<Footer />
</div>

<style>
	.changelog-prose :global(h1) {
		font-family: var(--font-serif);
		font-size: 2.5rem;
		line-height: 1.1;
		letter-spacing: -0.01em;
		color: var(--color-ink);
		margin-bottom: 0.5rem;
	}

	.changelog-prose :global(.lead) {
		color: var(--color-ink-soft);
		font-size: 1.05rem;
		line-height: 1.6;
		margin-bottom: 3rem;
	}

	.timeline {
		list-style: none;
		margin: 0;
		padding: 0;
		border-left: 2px solid var(--color-border);
	}

	.entry {
		position: relative;
		padding-left: 1.75rem;
		padding-bottom: 3.5rem;
		/* An anchored version should not land under the fixed header. */
		scroll-margin-top: 6rem;
	}

	.entry:last-child {
		padding-bottom: 0;
	}

	/* The dot on the timeline rail, aligned with the version heading. */
	.entry::before {
		content: '';
		position: absolute;
		left: -0.4rem;
		top: 0.55rem;
		width: 0.7rem;
		height: 0.7rem;
		border-radius: 50%;
		background: var(--color-primary);
	}

	.entry-head {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.25rem 0.75rem;
	}

	.changelog-prose :global(h2) {
		font-family: var(--font-serif);
		font-size: 1.6rem;
		line-height: 1.2;
		color: var(--color-ink);
		margin: 0;
	}

	/* Beats `.changelog-prose :global(a)` below, which underlines body links. */
	.changelog-prose .anchor {
		color: inherit;
		text-decoration: none;
	}

	.changelog-prose .anchor:hover {
		color: var(--color-primary);
	}

	.badge {
		display: inline-block;
		font-family: var(--font-sans);
		font-size: 0.7rem;
		font-weight: 600;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		color: var(--color-primary);
		background: var(--color-primary-soft);
		border-radius: 999px;
		padding: 0.15rem 0.55rem;
		vertical-align: 0.15em;
	}

	.changelog-prose :global(.meta) {
		font-size: 0.85rem;
		color: var(--color-ink-mute);
		margin: 0;
	}

	.summary {
		color: var(--color-ink);
		font-size: 1.02rem;
		line-height: 1.6;
		margin: 0.85rem 0 1.25rem;
	}

	.changelog-prose :global(h3) {
		font-family: var(--font-serif);
		font-size: 1.15rem;
		line-height: 1.3;
		color: var(--color-ink);
		margin-top: 1.75rem;
		margin-bottom: 0.5rem;
	}

	.changelog-prose :global(p),
	.changelog-prose :global(li) {
		color: var(--color-ink-soft);
		line-height: 1.7;
	}

	.changelog-prose :global(p) {
		margin-bottom: 1rem;
	}

	.changelog-prose :global(.entry ul) {
		margin-bottom: 1rem;
		padding-left: 1.25rem;
		list-style-type: disc;
	}

	.changelog-prose :global(.entry li) {
		margin-bottom: 0.5rem;
	}

	.changelog-prose :global(a) {
		color: var(--color-primary);
		text-decoration: underline;
		text-underline-offset: 2px;
	}

	.changelog-prose :global(a:hover) {
		color: var(--color-primary-hover);
	}

	.changelog-prose :global(strong) {
		color: var(--color-ink);
		font-weight: 600;
	}

	.changelog-prose :global(code) {
		font-family: var(--font-mono, ui-monospace, monospace);
		font-size: 0.9em;
		background: var(--color-surface, rgba(0, 0, 0, 0.04));
		padding: 0.1em 0.35em;
		border-radius: 3px;
	}
</style>
