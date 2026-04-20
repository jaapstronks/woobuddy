<script lang="ts">
	import { ArrowUpRight } from 'lucide-svelte';
	import { reveal } from '$lib/actions/reveal';
	import LeadCaptureForm from '$lib/components/marketing/LeadCaptureForm.svelte';
	import GithubIcon from '$lib/components/ui/GithubIcon.svelte';
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
					<GithubIcon size={16} />
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
