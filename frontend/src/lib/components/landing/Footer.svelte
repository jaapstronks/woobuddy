<script lang="ts">
	import Logo from '$lib/components/shared/Logo.svelte';
</script>

<footer class="border-t border-gray-200 bg-white px-6 py-12">
	<div class="mx-auto flex max-w-6xl flex-col items-center gap-6 sm:flex-row sm:justify-between">
		<Logo size="small" />

		<nav class="flex gap-6 text-sm text-neutral">
			<a href="https://github.com/jaapstronks/woobuddy" class="hover:text-primary" target="_blank" rel="noopener noreferrer">GitHub</a>
			<a href="/app" class="hover:text-primary">App</a>
		</nav>

		<p class="text-xs text-gray-400">
			MIT License &middot; WOO Buddy
		</p>
	</div>
</footer>
