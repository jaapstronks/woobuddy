<script lang="ts">
	import Logo from '$lib/components/shared/Logo.svelte';
</script>

<header
	class="fixed top-0 right-0 left-0 z-50 border-b border-border bg-bg/85 backdrop-blur-md"
>
	<div class="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
		<Logo />
		<nav class="flex items-center gap-6">
			<a
				href="#privacy"
				class="hidden text-sm text-ink-soft transition-colors hover:text-ink sm:inline"
			>
				Privacy
			</a>
			<a
				href="https://github.com/jaapstronks/woobuddy"
				target="_blank"
				rel="noopener noreferrer"
				class="hidden text-sm text-ink-soft transition-colors hover:text-ink sm:inline"
			>
				Open source
			</a>
			<a
				href="#updates"
				class="hidden text-sm text-ink-soft transition-colors hover:text-ink sm:inline"
			>
				Updates
			</a>
			<a
				href="/try"
				class="rounded-md border border-ink bg-ink px-4 py-2 text-sm font-medium text-bg transition-colors hover:bg-primary hover:border-primary"
			>
				Open in browser
			</a>
		</nav>
	</div>
</header>
