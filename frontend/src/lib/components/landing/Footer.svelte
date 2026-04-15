<script lang="ts">
	import Logo from '$lib/components/shared/Logo.svelte';
</script>

<footer class="border-t border-border bg-bg px-6 py-12">
	<div class="mx-auto max-w-6xl">
		<div class="flex flex-col items-start gap-8 sm:flex-row sm:items-center sm:justify-between">
			<div>
				<Logo size="small" />
				<p class="mt-3 max-w-sm text-xs leading-relaxed text-ink-mute">
					Privacyvriendelijk lakgereedschap voor Woo-documenten. Werkt in je browser.
					Geen upload, geen AI, geen trackers.
				</p>
			</div>

			<nav class="flex flex-wrap gap-x-6 gap-y-2 text-sm text-ink-soft">
				<a href="#privacy" class="hover:text-ink">Privacy</a>
				<a
					href="https://github.com/jaapstronks/woobuddy"
					class="hover:text-ink"
					target="_blank"
					rel="noopener noreferrer">GitHub</a
				>
				<a href="#try" class="hover:text-ink">Probeer</a>
			</nav>
		</div>

		<div class="mt-10 border-t border-border pt-6 text-xs text-ink-mute">
			<p>MIT License · WOO Buddy</p>
		</div>
	</div>
</footer>
