<script lang="ts">
	import { Github, Server, Lock } from 'lucide-svelte';

	const features = [
		{
			icon: Lock,
			title: 'Data blijft bij jou',
			description: 'Draai WOO Buddy op je eigen servers. Documenten verlaten nooit je netwerk.'
		},
		{
			icon: Server,
			title: 'Eén commando',
			description: 'docker compose up — en je bent klaar. Geen complexe installatie.'
		},
		{
			icon: Github,
			title: 'Open source',
			description: 'MIT-licentie. Bekijk de code, pas aan, draag bij. Volledig transparant.'
		}
	];
</script>

<section class="bg-bg px-6 py-24">
	<div class="mx-auto max-w-6xl">
		<h2 class="text-center text-3xl font-bold text-gray-900">Open source & zelf hosten</h2>
		<p class="mx-auto mt-4 max-w-2xl text-center text-neutral">
			WOO Buddy is ontworpen voor organisaties die controle willen houden over hun data.
		</p>

		<div class="mt-16 grid grid-cols-1 gap-8 sm:grid-cols-3">
			{#each features as feature}
				<div class="flex flex-col items-center text-center">
					<div
						class="flex h-14 w-14 items-center justify-center rounded-2xl bg-landing-accent text-primary"
					>
						<feature.icon size={28} />
					</div>
					<h3 class="mt-4 text-lg font-semibold text-gray-900">{feature.title}</h3>
					<p class="mt-2 text-sm leading-relaxed text-neutral">{feature.description}</p>
				</div>
			{/each}
		</div>

		<div class="mt-12 text-center">
			<a
				href="https://github.com/jaapstronks/woobuddy"
				target="_blank"
				rel="noopener noreferrer"
				class="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-6 py-3 text-sm font-medium text-gray-700 transition-colors hover:border-primary hover:text-primary"
			>
				<Github size={20} />
				Bekijk op GitHub
			</a>
		</div>
	</div>
</section>
