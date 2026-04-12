<script lang="ts">
	// Shoelace: theme CSS + icon base path (components imported where used)
	import '@shoelace-style/shoelace/dist/themes/light.css';
	import { setBasePath } from '@shoelace-style/shoelace/dist/utilities/base-path.js';

	setBasePath('https://cdn.jsdelivr.net/npm/@shoelace-style/shoelace@2.20.1/cdn/');

	let { children } = $props();
</script>

<div class="flex h-screen flex-col overflow-hidden bg-bg">
	{@render children()}
</div>
