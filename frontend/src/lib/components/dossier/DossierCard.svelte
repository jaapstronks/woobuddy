<script lang="ts">
	import { FolderOpen, FileText, Clock } from 'lucide-svelte';
	import type { Dossier } from '$lib/types';
	import { DOSSIER_STATUS_LABELS } from '$lib/utils/status';
	import { formatDate } from '$lib/utils/format';

	let { dossier }: { dossier: Dossier } = $props();

	const status = $derived(DOSSIER_STATUS_LABELS[dossier.status] ?? DOSSIER_STATUS_LABELS.open);
</script>

<a
	href="/app/dossier/{dossier.id}"
	class="group block rounded-xl border border-gray-200 bg-white p-6 transition-all hover:border-primary/30 hover:shadow-md"
>
	<div class="flex items-start justify-between">
		<div class="flex items-center gap-3">
			<div class="flex h-10 w-10 items-center justify-center rounded-lg bg-landing-accent text-primary">
				<FolderOpen size={20} />
			</div>
			<div>
				<h3 class="font-semibold text-gray-900 group-hover:text-primary">{dossier.title}</h3>
				<p class="text-sm text-neutral">{dossier.request_number}</p>
			</div>
		</div>
		<span class="rounded-full px-2.5 py-1 text-xs font-medium {status.color}">
			{status.label}
		</span>
	</div>

	<div class="mt-4 flex items-center gap-4 text-xs text-neutral">
		<span class="flex items-center gap-1">
			<FileText size={14} />
			{dossier.organization}
		</span>
		<span class="flex items-center gap-1">
			<Clock size={14} />
			{formatDate(dossier.created_at)}
		</span>
	</div>
</a>
