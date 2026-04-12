<script lang="ts">
	import '@shoelace-style/shoelace/dist/components/button/button.js';
	import '@shoelace-style/shoelace/dist/components/textarea/textarea.js';

	interface Props {
		detectionId: string;
		initialText: string;
		onSave: (id: string, text: string) => void;
	}

	let { detectionId, initialText, onSave }: Props = $props();

	// Intentionally seeds local state from the initial prop value; the $effect
	// below re-seeds it whenever detectionId changes.
	// svelte-ignore state_referenced_locally
	let text = $state(initialText);
	const dirty = $derived(text !== initialText);

	// Reset when switching to a different detection
	$effect(() => {
		// Re-run when detectionId changes
		detectionId;
		text = initialText;
	});
</script>

<div class="rounded-lg border border-gray-200 bg-white p-3">
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<sl-textarea
		label="Motiveringstekst"
		value={text}
		rows="4"
		onsl-input={(e: Event) => { text = (e.target as HTMLTextAreaElement).value; }}
	></sl-textarea>
	{#if dirty}
		<div class="mt-2 flex justify-end">
			<sl-button size="small" variant="primary" onclick={() => onSave(detectionId, text)}>
				Opslaan
			</sl-button>
		</div>
	{/if}
</div>
