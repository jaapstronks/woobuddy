<script lang="ts">
	import { ArrowUpRight } from 'lucide-svelte';
	import { reveal } from '$lib/actions/reveal';
	import LeadCaptureForm from '$lib/components/marketing/LeadCaptureForm.svelte';
</script>

<section id="privacy" class="px-6 py-24">
	<div class="mx-auto max-w-3xl">
		<div use:reveal>
			<p class="text-sm font-medium tracking-wide text-primary uppercase">Open source</p>
			<h2 class="mt-3 font-serif text-4xl tracking-tight text-ink sm:text-5xl">
				Lees de code, niet onze beloftes.
			</h2>
			<p class="mt-6 text-lg leading-relaxed text-ink-soft">
				Privacy is geen feature die we hebben aangezet — het is hoe het ding gebouwd is.
				Architectuur, niet beleid. WOO Buddy is volledig open source onder MIT-licentie,
				dus je kunt zelf controleren dat we doen wat we zeggen — of de hele zaak op je
				eigen infrastructuur draaien.
			</p>

			<div class="mt-8">
				<a
					href="https://github.com/jaapstronks/woobuddy"
					target="_blank"
					rel="noopener noreferrer"
					class="inline-flex items-center gap-2 rounded-md border border-ink bg-ink px-5 py-3 text-sm font-medium text-bg transition-colors hover:bg-primary hover:border-primary"
				>
					<svg
						width="16"
						height="16"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="2"
						stroke-linecap="round"
						stroke-linejoin="round"
						aria-hidden="true"
					>
						<path
							d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4"
						/>
						<path d="M9 18c-4.51 2-5-2-7-2" />
					</svg>
					Bekijk op GitHub
					<ArrowUpRight size={14} />
				</a>
			</div>
		</div>

		<div
			id="updates"
			class="mt-16 border-t border-border pt-12"
			use:reveal={{ delay: 120 }}
		>
			<h3 class="font-serif text-2xl text-ink">
				De tool is gratis. Teamfuncties komen eraan.
			</h3>
			<p class="mt-4 text-base leading-relaxed text-ink-soft">
				WOO Buddy blijft gratis voor individuele Woo-reviewers. Geïnteresseerd in gedeelde
				woordenlijsten, audit log, multi-user review of een NL-gehoste versie voor je
				gemeente? Laat je e-mailadres achter — geen nieuwsbrief, alleen een bericht als er
				écht iets te melden is.
			</p>

			<div class="mt-8">
				<LeadCaptureForm source="landing" />
			</div>
		</div>
	</div>
</section>
