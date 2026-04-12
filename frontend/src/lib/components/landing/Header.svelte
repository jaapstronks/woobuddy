<script lang="ts">
	import Logo from '$lib/components/shared/Logo.svelte';
</script>

<header class="fixed top-0 left-0 right-0 z-50 bg-white/80 backdrop-blur-md border-b border-gray-100">
	<div class="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
		<Logo />
		<a
			href="/try"
			class="rounded-lg bg-primary px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary-light"
		>
			Probeer gratis
		</a>
	</div>
</header>
