<script lang="ts">
	import { Upload, X } from 'lucide-svelte';
	import type { PublicOfficial } from '$lib/types';

	interface Props {
		officials: PublicOfficial[];
		loading: boolean;
		onUpload: (file: File) => void;
		onRemove: (id: string) => void;
	}

	let { officials, loading, onUpload, onRemove }: Props = $props();

	let fileInput = $state<HTMLInputElement | null>(null);

	function handleFileSelect(e: Event) {
		const input = e.target as HTMLInputElement;
		if (input.files?.[0]) {
			onUpload(input.files[0]);
			input.value = '';
		}
	}
</script>

<div>
	<div class="mb-3 flex items-center justify-between">
		<h3 class="text-sm font-semibold text-gray-900">Publieke functionarissen</h3>
		<button
			class="flex items-center gap-1 rounded border border-gray-300 px-2 py-1 text-xs text-neutral hover:border-primary hover:text-primary"
			onclick={() => fileInput?.click()}
			disabled={loading}
		>
			<Upload size={12} />
			CSV uploaden
		</button>
		<input
			bind:this={fileInput}
			type="file"
			accept=".csv"
			class="hidden"
			onchange={handleFileSelect}
		/>
	</div>

	<p class="mb-3 text-xs text-neutral">
		Namen op deze lijst worden NIET gelakt. Upload een CSV met kolommen: naam, rol.
	</p>

	{#if officials.length > 0}
		<div class="space-y-1">
			{#each officials as official (official.id)}
				<div class="flex items-center justify-between rounded bg-gray-50 px-3 py-1.5 text-sm">
					<div>
						<span class="font-medium">{official.name}</span>
						{#if official.role}
							<span class="ml-2 text-xs text-neutral">{official.role}</span>
						{/if}
					</div>
					<button
						class="text-neutral hover:text-danger"
						onclick={() => onRemove(official.id)}
					>
						<X size={14} />
					</button>
				</div>
			{/each}
		</div>
	{:else}
		<p class="text-xs italic text-neutral">Nog geen functionarissen toegevoegd.</p>
	{/if}
</div>
