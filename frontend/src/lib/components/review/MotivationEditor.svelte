<script lang="ts">
	interface Props {
		detectionId: string;
		initialText: string;
		onSave: (id: string, text: string) => void;
	}

	let { detectionId, initialText, onSave }: Props = $props();

	let text = $state(initialText);
	let dirty = $derived(text !== initialText);
</script>

<div class="rounded-lg border border-gray-200 bg-white p-3">
	<label class="mb-1 block text-xs font-medium text-neutral" for="motivation-{detectionId}">
		Motiveringstekst
	</label>
	<textarea
		id="motivation-{detectionId}"
		bind:value={text}
		class="w-full rounded border border-gray-200 p-2 text-sm leading-relaxed focus:border-primary focus:outline-none"
		rows="4"
	></textarea>
	{#if dirty}
		<div class="mt-2 flex justify-end">
			<button
				class="rounded bg-primary px-3 py-1 text-xs text-white hover:bg-primary-light"
				onclick={() => onSave(detectionId, text)}
			>
				Opslaan
			</button>
		</div>
	{/if}
</div>
