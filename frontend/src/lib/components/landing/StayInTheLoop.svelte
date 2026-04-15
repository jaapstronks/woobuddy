<script lang="ts">
	import { reveal } from '$lib/actions/reveal';
	import LeadCaptureForm from '$lib/components/marketing/LeadCaptureForm.svelte';
</script>

<section id="updates" class="px-6 py-24">
	<div class="mx-auto max-w-3xl">
		<div use:reveal>
			<p class="text-sm font-medium tracking-wide text-primary uppercase">Blijf op de hoogte</p>
			<h2 class="mt-3 font-serif text-4xl tracking-tight text-ink sm:text-5xl">
				De tool is gratis. Teamfuncties komen eraan.
			</h2>
			<p class="mt-6 text-lg leading-relaxed text-ink-soft">
				WOO Buddy blijft gratis voor individuele Woo-reviewers — ook na de launch
				van betaalde teamfuncties. Als je geïnteresseerd bent in gedeelde
				woordenlijsten, audit log, multi-user review of een NL-gehoste versie voor
				je gemeente, laat dan je e-mailadres achter. Dan mailen we je zodra het
				zover is.
			</p>
			<p class="mt-3 text-sm text-ink-mute">
				Geen nieuwsbrief, geen spam, geen tracking. Alleen een bericht wanneer er
				écht iets te melden is.
			</p>
		</div>

		<div class="mt-10" use:reveal={{ delay: 120 }}>
			<LeadCaptureForm source="landing" />
		</div>
	</div>
</section>
