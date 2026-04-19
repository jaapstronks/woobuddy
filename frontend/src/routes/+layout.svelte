<script lang="ts">
	import '../app.css';
	import { onMount } from 'svelte';
	import { afterNavigate } from '$app/navigation';
	import { PUBLIC_PLAUSIBLE_DOMAIN, PUBLIC_PLAUSIBLE_SRC } from '$env/static/public';
	import { pageview, isEnabled as analyticsEnabled } from '$lib/analytics/plausible';

	let { children } = $props();

	// Inject the Plausible script client-side only, and only when configured.
	// The `manual` variant gives us control over the URL that lands in the
	// dashboard — see normalizePath() in $lib/analytics/plausible.ts, which
	// collapses /review/<uuid> into /review/:docId so one row per document
	// doesn't explode the Top Pages view.
	onMount(() => {
		if (!analyticsEnabled()) return;
		if (document.querySelector('script[data-plausible]')) {
			pageview();
			return;
		}
		const script = document.createElement('script');
		script.defer = true;
		script.src = PUBLIC_PLAUSIBLE_SRC;
		script.setAttribute('data-domain', PUBLIC_PLAUSIBLE_DOMAIN);
		script.setAttribute('data-plausible', 'true');
		script.addEventListener('load', () => pageview());
		document.head.appendChild(script);
	});

	afterNavigate(() => {
		pageview();
	});
</script>

{@render children()}
