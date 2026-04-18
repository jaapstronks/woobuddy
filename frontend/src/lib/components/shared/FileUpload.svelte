<script lang="ts">
	import { FileDown, FileText, Lock, X } from 'lucide-svelte';
	import ProviderPickerButtons from './ProviderPickerButtons.svelte';

	let {
		accept = '.pdf',
		maxSizeMb = 50,
		multiple = false,
		onfiles,
		/**
		 * Show the SharePoint / Drive picker buttons below the drop
		 * zone. Only renders buttons for providers that are actually
		 * configured (see `$lib/config/file-picker.ts`). Defaults to
		 * false so embedders that don't want the extra surface —
		 * e.g. places where a picked file wouldn't make sense — can
		 * opt out.
		 */
		showProviderPickers = false
	}: {
		accept?: string;
		maxSizeMb?: number;
		multiple?: boolean;
		onfiles: (files: File[]) => void;
		showProviderPickers?: boolean;
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

	function handleProviderPick(file: File) {
		handleFiles([file]);
	}
</script>

<div class="flex h-full flex-col gap-3">
	<!-- Drop zone -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="drop-zone flex min-h-[14rem] flex-1 cursor-pointer flex-col items-center justify-center rounded-md border border-dashed px-8 py-14 transition-all duration-200 ease-out
			{dragging
			? 'border-primary bg-primary-soft scale-[1.015]'
			: 'border-border-strong bg-surface breathe-pulse hover:border-primary hover:bg-primary-soft/40'}"
		ondrop={handleDrop}
		ondragover={handleDragOver}
		ondragleave={handleDragLeave}
		onclick={openPicker}
		onkeydown={(e) => e.key === 'Enter' && openPicker()}
		role="button"
		tabindex="0"
	>
		<FileDown size={32} class={dragging ? 'text-primary' : 'text-ink-mute'} strokeWidth={1.5} />
		<span class="mt-4 font-serif text-xl {dragging ? 'text-primary' : 'text-ink'}">
			Sleep {multiple ? "PDF's" : 'een PDF'} in je browser
		</span>
		<span class="mt-1 text-sm text-ink-soft">of klik om te bladeren · max. {maxSizeMb} MB</span>

		<!-- Trust micro-line. The dashed border + "Sleep...hierheen" pattern is
		     universally read as "upload target", which is the opposite of what
		     WOO Buddy does. Putting the reassurance inside the zone answers
		     the "wait, is this sending my PDF somewhere?" question at the
		     exact moment the reviewer is about to drop a file. -->
		<span
			class="mt-5 inline-flex items-center gap-1.5 rounded-full border border-border bg-bg px-2.5 py-1 text-[11px] font-medium text-ink-soft"
		>
			<Lock size={11} class="text-primary" strokeWidth={2} />
			Blijft op je apparaat — geen upload
		</span>
	</div>

	<input
		bind:this={inputEl}
		type="file"
		{accept}
		{multiple}
		style="display: none;"
		onchange={handleInputChange}
	/>

	{#if showProviderPickers}
		<ProviderPickerButtons onfile={handleProviderPick} />
	{/if}

	<!-- Error -->
	{#if error}
		<p class="text-sm text-danger">{error}</p>
	{/if}

	<!-- Selected files -->
	{#if selectedFiles.length > 0}
		<ul class="space-y-2">
			{#each selectedFiles as file, i}
				<li class="flex items-center justify-between rounded-md border border-border bg-surface px-4 py-3">
					<div class="flex items-center gap-3">
						<FileText size={18} class="text-primary" strokeWidth={1.5} />
						<div>
							<p class="text-sm font-medium text-ink">{file.name}</p>
							<p class="text-xs text-ink-mute">{(file.size / 1024 / 1024).toFixed(1)} MB · blijft op deze computer</p>
						</div>
					</div>
					<button
						onclick={() => removeFile(i)}
						class="rounded p-1 text-ink-mute transition-colors hover:bg-bg hover:text-danger"
						aria-label="Verwijder {file.name}"
					>
						<X size={16} />
					</button>
				</li>
			{/each}
		</ul>
	{/if}
</div>
