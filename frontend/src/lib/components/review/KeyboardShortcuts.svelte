<script lang="ts">
	import '@shoelace-style/shoelace/dist/components/button/button.js';
	import '@shoelace-style/shoelace/dist/components/dialog/dialog.js';

	import { onMount, onDestroy } from 'svelte';

	interface Props {
		onAccept: () => void;
		onReject: () => void;
		onDefer: () => void;
		onNext: () => void;
		onPrev: () => void;
		onToggleHelp: () => void;
	}

	let { onAccept, onReject, onDefer, onNext, onPrev, onToggleHelp }: Props = $props();

	let showHelp = $state(false);

	function handleKeydown(e: KeyboardEvent) {
		// Skip when typing in an input/textarea/select
		const tag = (e.target as HTMLElement)?.tagName;
		if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

		switch (e.key.toLowerCase()) {
			case 'a':
				e.preventDefault();
				onAccept();
				break;
			case 'r':
				e.preventDefault();
				onReject();
				break;
			case 'd':
				e.preventDefault();
				onDefer();
				break;
			case 'arrowright':
				e.preventDefault();
				onNext();
				break;
			case 'arrowleft':
				e.preventDefault();
				onPrev();
				break;
			case '?':
				e.preventDefault();
				showHelp = !showHelp;
				onToggleHelp();
				break;
		}
	}

	onMount(() => {
		window.addEventListener('keydown', handleKeydown);
	});

	onDestroy(() => {
		window.removeEventListener('keydown', handleKeydown);
	});
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<sl-dialog label="Sneltoetsen" open={showHelp} onsl-request-close={() => (showHelp = false)}>
	<div class="space-y-2 text-sm">
		<div class="flex justify-between">
			<span>Accepteren / Lakken</span>
			<kbd class="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs">A</kbd>
		</div>
		<div class="flex justify-between">
			<span>Afwijzen / Niet lakken</span>
			<kbd class="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs">R</kbd>
		</div>
		<div class="flex justify-between">
			<span>Uitstellen</span>
			<kbd class="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs">D</kbd>
		</div>
		<div class="flex justify-between">
			<span>Volgende detectie</span>
			<kbd class="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs">&rarr;</kbd>
		</div>
		<div class="flex justify-between">
			<span>Vorige detectie</span>
			<kbd class="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs">&larr;</kbd>
		</div>
		<div class="flex justify-between">
			<span>Dit venster</span>
			<kbd class="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs">?</kbd>
		</div>
	</div>
	<sl-button slot="footer" variant="primary" onclick={() => (showHelp = false)}>
		Sluiten
	</sl-button>
</sl-dialog>
