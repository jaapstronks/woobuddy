<script lang="ts">
	import Logo from '$lib/components/shared/Logo.svelte';
	import GithubIcon from '$lib/components/ui/GithubIcon.svelte';
	import { isHosted } from '$lib/config/site';

	const hosted = isHosted();
</script>

<footer class="border-t border-border bg-bg px-6 py-12">
	<div class="mx-auto max-w-6xl">
		<div class="flex flex-col items-start gap-8 sm:flex-row sm:items-start sm:justify-between">
			<div>
				<Logo size="small" />
				<p class="mt-3 max-w-sm text-xs leading-relaxed text-ink-mute">
					Privacyvriendelijk lakgereedschap voor Woo-documenten. Werkt in je browser. Geen
					upload, geen AI, geen advertentietrackers.
				</p>
				{#if hosted}
					<p class="mt-3 max-w-sm text-xs leading-relaxed text-ink-mute">
						WOO Buddy gebruikt alleen functionele cookies.
						<a href="/cookies" class="underline hover:text-ink">Meer informatie</a>.
					</p>
				{/if}
			</div>

			<nav
				class="grid grid-cols-2 gap-x-8 gap-y-2 text-sm text-ink-soft sm:grid-cols-[auto_auto]"
			>
				{#if hosted}
					<a href="/privacy" class="hover:text-ink">Privacy</a>
					<a href="/terms" class="hover:text-ink">Voorwaarden</a>
					<a href="/cookies" class="hover:text-ink">Cookies</a>
					<a href="/verwerkersovereenkomst" class="hover:text-ink">Verwerkersovereenkomst</a>
					<a href="/roadmap" class="hover:text-ink">Roadmap</a>
				{/if}
				<a
					href="https://github.com/jaapstronks/woobuddy"
					class="flex items-center hover:text-ink"
					target="_blank"
					rel="noopener noreferrer"
					aria-label="WOO Buddy op GitHub"
				>
					<GithubIcon size={16} />
				</a>
				<a href="/#try" class="hover:text-ink">Probeer</a>
			</nav>
		</div>

		<div class="mt-10 border-t border-border pt-6 text-xs text-ink-mute">
			<p>MIT License · WOO Buddy</p>
		</div>
	</div>
</footer>
