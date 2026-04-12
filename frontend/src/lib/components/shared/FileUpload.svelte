<script lang="ts">
	import { Upload, FileText, X } from 'lucide-svelte';

	let {
		accept = '.pdf',
		maxSizeMb = 50,
		multiple = false,
		onfiles
	}: {
		accept?: string;
		maxSizeMb?: number;
		multiple?: boolean;
		onfiles: (files: File[]) => void;
	} = $props();

	let dragging = $state(false);
	let error = $state<string | null>(null);
	let selectedFiles = $state<File[]>([]);
	let inputEl: HTMLInputElement | undefined = $state();

	function validate(files: FileList | File[]): File[] {
		const valid: File[] = [];
		error = null;

		for (const file of files) {
			if (!file.name.toLowerCase().endsWith('.pdf')) {
				error = `${file.name} is geen PDF-bestand`;
				continue;
			}
			if (file.size > maxSizeMb * 1024 * 1024) {
				error = `${file.name} is groter dan ${maxSizeMb} MB`;
				continue;
			}
			valid.push(file);
		}

		return valid;
	}

	function handleFiles(files: FileList | File[]) {
		const valid = validate(files);
		if (valid.length > 0) {
			selectedFiles = multiple ? [...selectedFiles, ...valid] : valid;
			onfiles(selectedFiles);
		}
	}

	function handleDrop(e: DragEvent) {
		e.preventDefault();
		dragging = false;
		if (e.dataTransfer?.files) {
			handleFiles(e.dataTransfer.files);
		}
	}

	function handleDragOver(e: DragEvent) {
		e.preventDefault();
		dragging = true;
	}

	function handleDragLeave() {
		dragging = false;
	}

	function handleInputChange(e: Event) {
		const target = e.target as HTMLInputElement;
		if (target.files) {
			handleFiles(target.files);
		}
	}

	function removeFile(index: number) {
		selectedFiles = selectedFiles.filter((_, i) => i !== index);
		onfiles(selectedFiles);
	}

	function openPicker() {
		inputEl?.click();
	}
</script>

<div class="space-y-3">
	<!-- Drop zone -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-8 py-12 transition-all
			{dragging
			? 'border-primary bg-landing-accent'
			: 'border-gray-300 bg-gray-50 hover:border-primary hover:bg-landing-accent/50'}"
		ondrop={handleDrop}
		ondragover={handleDragOver}
		ondragleave={handleDragLeave}
		onclick={openPicker}
		onkeydown={(e) => e.key === 'Enter' && openPicker()}
		role="button"
		tabindex="0"
	>
		<Upload size={40} class={dragging ? 'text-primary' : 'text-gray-400'} />
		<span class="mt-3 text-base font-medium {dragging ? 'text-primary' : 'text-gray-700'}">
			Sleep {multiple ? 'PDF\'s' : 'een PDF'} hierheen
		</span>
		<span class="mt-1 text-sm text-neutral">of klik om te selecteren (max. {maxSizeMb} MB)</span>
	</div>

	<input
		bind:this={inputEl}
		type="file"
		{accept}
		{multiple}
		style="display: none;"
		onchange={handleInputChange}
	/>

	<!-- Error -->
	{#if error}
		<p class="text-sm text-danger">{error}</p>
	{/if}

	<!-- Selected files -->
	{#if selectedFiles.length > 0}
		<ul class="space-y-2">
			{#each selectedFiles as file, i}
				<li class="flex items-center justify-between rounded-lg border border-gray-200 bg-white px-4 py-3">
					<div class="flex items-center gap-3">
						<FileText size={18} class="text-primary" />
						<div>
							<p class="text-sm font-medium text-gray-900">{file.name}</p>
							<p class="text-xs text-neutral">{(file.size / 1024 / 1024).toFixed(1)} MB</p>
						</div>
					</div>
					<button
						onclick={() => removeFile(i)}
						class="rounded p-1 text-neutral transition-colors hover:bg-gray-100 hover:text-danger"
						aria-label="Verwijder {file.name}"
					>
						<X size={16} />
					</button>
				</li>
			{/each}
		</ul>
	{/if}
</div>
