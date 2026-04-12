<script lang="ts">
	import { Download, FileText } from 'lucide-svelte';
	import { getExportDownloadUrl, getMotivationReportUrl } from '$lib/api/client';

	interface Props {
		dossierId: string;
		exporting: boolean;
		onExport: () => void;
	}

	let { dossierId, exporting, onExport }: Props = $props();

	const exportUrl = $derived(getExportDownloadUrl(dossierId));
	const reportUrl = $derived(getMotivationReportUrl(dossierId));
</script>

<div class="space-y-6">
	<!-- Export action -->
	<div class="rounded-xl border border-gray-200 bg-white p-6">
		<h2 class="flex items-center gap-2 text-lg font-semibold text-gray-900">
			<FileText size={20} />
			Exporteren
		</h2>
		<p class="mt-2 text-sm text-neutral">
			Genereer een ZIP-bestand met alle gelakte PDF's en het motiveringsrapport.
		</p>

		<button
			class="mt-4 flex items-center gap-2 rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary-light disabled:opacity-50"
			onclick={onExport}
			disabled={exporting}
		>
			{#if exporting}
				<div class="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent"></div>
				Exporteren...
			{:else}
				<Download size={16} />
				Export starten
			{/if}
		</button>
	</div>

	<!-- Download links -->
	<div class="rounded-xl border border-gray-200 bg-white p-6">
		<h3 class="text-sm font-semibold text-gray-900">Downloads</h3>
		<div class="mt-3 space-y-2">
			<a
				href={exportUrl}
				class="flex items-center gap-2 rounded-lg border border-gray-200 px-4 py-3 text-sm transition-colors hover:border-primary hover:bg-primary/5"
				download
			>
				<Download size={16} class="text-primary" />
				<div>
					<p class="font-medium">Gelakte documenten (ZIP)</p>
					<p class="text-xs text-neutral">Alle PDF's met toegepaste lakken</p>
				</div>
			</a>

			<a
				href={reportUrl}
				class="flex items-center gap-2 rounded-lg border border-gray-200 px-4 py-3 text-sm transition-colors hover:border-primary hover:bg-primary/5"
				download
			>
				<FileText size={16} class="text-primary" />
				<div>
					<p class="font-medium">Motiveringsrapport</p>
					<p class="text-xs text-neutral">Gestructureerde motivering per Woo-artikel</p>
				</div>
			</a>
		</div>
	</div>
</div>
