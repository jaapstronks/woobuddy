<script lang="ts">
	import { Github, ArrowUpRight, Check, X } from 'lucide-svelte';
	import { reveal } from '$lib/actions/reveal';

	const yes = [
		'Tekstextractie gebeurt in jouw browser via pdf.js',
		'De server ziet alleen losse woorden — nooit hele zinnen, nooit pagina-context',
		'PDF wordt in het geheugen gelakt en direct teruggestuurd, nooit op disk geschreven',
		'Database bewaart alleen coördinaten en beslissingen — geen tekstinhoud',
		'AVG/GDPR-proof by design: je hoeft geen DPIA voor cloudverwerking te schrijven',
		'Open source onder MIT-licentie — controleer alles zelf'
	];

	const no = [
		'Geen AI of taalmodellen in de actieve pijplijn',
		'Geen Google Analytics, Plausible, Hotjar of andere trackers',
		'Geen cookies (echt: nul, ook geen "essentiële")',
		'Geen third-party fonts, scripts of CDN-calls',
		'Geen account, geen e-mailadres, geen registratie',
		'Geen telemetrie naar onze servers'
	];
</script>

<section id="privacy" class="px-6 py-24">
	<div class="mx-auto max-w-6xl">
		<div class="max-w-2xl" use:reveal>
			<p class="text-sm font-medium tracking-wide text-primary uppercase">Privacy by design</p>
			<h2 class="mt-3 font-serif text-4xl tracking-tight text-ink sm:text-5xl">
				Wat erin gaat, en wat er uitdrukkelijk niet in zit.
			</h2>
			<p class="mt-6 text-lg leading-relaxed text-ink-soft">
				Privacy is geen feature die we hebben aangezet — het is hoe het ding gebouwd is.
				Architectuur, niet beleid.
			</p>
		</div>

		<div class="mt-16 grid grid-cols-1 gap-px overflow-hidden rounded-lg border border-border bg-border md:grid-cols-2">
			<!-- Yes column -->
			<div class="bg-surface p-8" use:reveal>
				<div class="flex items-center gap-2 text-sm font-medium tracking-wide text-success uppercase">
					<Check size={16} strokeWidth={2.5} />
					Wel
				</div>
				<ul class="mt-6 space-y-4">
					{#each yes as item}
						<li class="flex gap-3 text-sm leading-relaxed text-ink">
							<Check size={16} class="mt-0.5 shrink-0 text-success" strokeWidth={2.5} />
							<span>{item}</span>
						</li>
					{/each}
				</ul>
			</div>

			<!-- No column -->
			<div class="bg-bg p-8" use:reveal={{ delay: 120 }}>
				<div class="flex items-center gap-2 text-sm font-medium tracking-wide text-ink-soft uppercase">
					<X size={16} strokeWidth={2.5} />
					Niet
				</div>
				<ul class="mt-6 space-y-4">
					{#each no as item}
						<li class="flex gap-3 text-sm leading-relaxed text-ink-soft">
							<X size={16} class="mt-0.5 shrink-0 text-ink-mute" strokeWidth={2.5} />
							<span>{item}</span>
						</li>
					{/each}
				</ul>
			</div>
		</div>

		<div
			class="mt-12 flex flex-col items-start justify-between gap-6 rounded-lg border border-border bg-surface p-8 sm:flex-row sm:items-center"
			use:reveal
		>
			<div class="max-w-xl">
				<h3 class="font-serif text-2xl text-ink">Lees de code, niet onze beloftes.</h3>
				<p class="mt-2 text-sm leading-relaxed text-ink-soft">
					WOO Buddy is volledig open source onder MIT-licentie. Je kunt zelf controleren
					dat we doen wat we zeggen — of de hele zaak op je eigen infrastructuur draaien.
				</p>
			</div>
			<a
				href="https://github.com/jaapstronks/woobuddy"
				target="_blank"
				rel="noopener noreferrer"
				class="inline-flex shrink-0 items-center gap-2 rounded-md border border-ink bg-ink px-5 py-3 text-sm font-medium text-bg transition-colors hover:bg-primary hover:border-primary"
			>
				<Github size={16} />
				Bekijk op GitHub
				<ArrowUpRight size={14} />
			</a>
		</div>
	</div>
</section>
