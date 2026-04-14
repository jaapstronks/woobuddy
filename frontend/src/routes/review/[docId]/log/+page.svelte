<script lang="ts">
	/**
	 * Redaction log (#19) — tabular oversight view of every detection in the
	 * current document. A separate tool from the review sidebar: reviewers and
	 * supervisors come here to check consistency, filter by grond/status, do
	 * bulk revisions, and eventually export the log as a motivation for the
	 * Woo-besluit.
	 *
	 * Client-first: no entity_text is shown. To see the actual passage the
	 * reviewer clicks "Bekijk" on a row, which jumps back into the review
	 * screen at that detection's page.
	 *
	 * Scope note: the spec was originally written against a dossier-level
	 * model. This project is deliberately single-document, so the log is
	 * scoped to one document. All filtering, sorting and pagination are
	 * performed client-side — typical single-document detection counts are
	 * comfortably in the hundreds, so the server-side pagination in the spec
	 * would be over-engineering at this point.
	 */

	import '@shoelace-style/shoelace/dist/components/button/button.js';
	import '@shoelace-style/shoelace/dist/components/select/select.js';
	import '@shoelace-style/shoelace/dist/components/option/option.js';
	import '@shoelace-style/shoelace/dist/components/checkbox/checkbox.js';
	import '@shoelace-style/shoelace/dist/components/dialog/dialog.js';
	import '@shoelace-style/shoelace/dist/components/tooltip/tooltip.js';
	import '@shoelace-style/shoelace/dist/components/spinner/spinner.js';

	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { detectionStore } from '$lib/stores/detections.svelte';
	import { reviewStore } from '$lib/stores/review.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import type {
		Detection,
		DetectionSource,
		DetectionTier,
		EntityType,
		ReviewStatus,
		WooArticleCode
	} from '$lib/types';
	import { TIERS } from '$lib/utils/tiers';
	import { WOO_ARTICLES, getArticleLabel } from '$lib/utils/woo-articles';
	import {
		ENTITY_TYPES,
		ENTITY_TYPE_ORDER,
		getEntityTypeBadgeClass,
		getEntityTypeLabel
	} from '$lib/utils/entity-types';
	import {
		DETECTION_SOURCES,
		REVIEW_STATUSES,
		REVIEW_STATUS_ORDER,
		getReviewStatusBadgeClass,
		getReviewStatusLabel,
		getSourceLabel,
		isAutoSource
	} from '$lib/utils/review-status';
	import { ArrowLeft, Eye, ChevronDown, ChevronRight, X, Trash2, Check, Ban, Clock } from 'lucide-svelte';

	const docId = $derived(page.params.docId!);

	$effect(() => {
		void docId;
		reviewStore.loadDocument(docId);
		// The detection store is a module-level singleton. If the reviewer
		// opened the log without first visiting the review screen (e.g. a
		// direct link), we still need to hydrate it from the server.
		detectionStore.load(docId);
	});

	// -----------------------------------------------------------------------
	// Local UI state (filters, sort, selection, expansion)
	//
	// Kept inside this component rather than the global detectionStore
	// because: (a) the review sidebar uses a different (simpler) filter
	// shape, and leaking log-specific filters back into it would confuse
	// the sidebar UI; (b) this state is ephemeral — it resets when the
	// reviewer leaves the log page, which is the correct UX.
	// -----------------------------------------------------------------------

	let filterTier = $state<DetectionTier | ''>('');
	let filterStatus = $state<ReviewStatus | ''>('');
	let filterEntityType = $state<EntityType | ''>('');
	let filterArticle = $state<WooArticleCode | ''>('');
	let filterSource = $state<DetectionSource | ''>('');
	let filterPage = $state<number | ''>('');

	type SortKey = 'index' | 'page' | 'entity_type' | 'tier' | 'woo_article' | 'review_status' | 'source' | 'reviewed_at';
	let sortKey = $state<SortKey>('page');
	let sortDir = $state<'asc' | 'desc'>('asc');

	let selectedIds = $state<Set<string>>(new Set());
	let expandedId = $state<string | null>(null);

	/** Bulk action confirmation state — drives the Shoelace dialog below. */
	type PendingBulk =
		| { kind: 'status'; status: ReviewStatus; label: string }
		| { kind: 'article'; article: WooArticleCode }
		| { kind: 'delete' }
		| null;
	let pendingBulk = $state<PendingBulk>(null);
	let bulkRunning = $state(false);

	// -----------------------------------------------------------------------
	// Derived: rows after filter + sort
	// -----------------------------------------------------------------------

	function firstPage(d: Detection): number {
		return d.bounding_boxes?.[0]?.page ?? -1;
	}

	const filtered = $derived.by(() => {
		let rows = detectionStore.all.slice();
		if (filterTier) rows = rows.filter((d) => d.tier === filterTier);
		if (filterStatus) rows = rows.filter((d) => d.review_status === filterStatus);
		if (filterEntityType) rows = rows.filter((d) => d.entity_type === filterEntityType);
		if (filterArticle) rows = rows.filter((d) => d.woo_article === filterArticle);
		if (filterSource) rows = rows.filter((d) => (d.source ?? 'regex') === filterSource);
		if (filterPage !== '') {
			// Match the 1-indexed page number the reviewer types in.
			const target = Number(filterPage) - 1;
			rows = rows.filter((d) => d.bounding_boxes?.some((b) => b.page === target));
		}
		return rows;
	});

	const hasFilters = $derived(
		filterTier !== '' ||
			filterStatus !== '' ||
			filterEntityType !== '' ||
			filterArticle !== '' ||
			filterSource !== '' ||
			filterPage !== ''
	);

	const sorted = $derived.by(() => {
		const rows = filtered.slice();
		const dir = sortDir === 'asc' ? 1 : -1;
		const cmp = (a: Detection, b: Detection): number => {
			switch (sortKey) {
				case 'index':
					// "Document order" — earliest bbox first, then tier, then id.
					return (
						(firstPage(a) - firstPage(b)) * dir ||
						a.tier.localeCompare(b.tier) * dir ||
						a.id.localeCompare(b.id) * dir
					);
				case 'page':
					return (firstPage(a) - firstPage(b)) * dir;
				case 'entity_type':
					return getEntityTypeLabel(a.entity_type).localeCompare(getEntityTypeLabel(b.entity_type)) * dir;
				case 'tier':
					return a.tier.localeCompare(b.tier) * dir;
				case 'woo_article':
					return (a.woo_article ?? '').localeCompare(b.woo_article ?? '') * dir;
				case 'review_status':
					return a.review_status.localeCompare(b.review_status) * dir;
				case 'source':
					return (a.source ?? '').localeCompare(b.source ?? '') * dir;
				case 'reviewed_at': {
					const ta = a.reviewed_at ? Date.parse(a.reviewed_at) : 0;
					const tb = b.reviewed_at ? Date.parse(b.reviewed_at) : 0;
					return (ta - tb) * dir;
				}
			}
		};
		rows.sort(cmp);
		return rows;
	});

	// -----------------------------------------------------------------------
	// Derived: filter-aware statistics bar
	//
	// The spec calls for the stats bar to reflect the current filter set so
	// supervisors can answer questions like "of the 37 Tier-2 persoon rows,
	// how many are still pending?". We compute everything from `filtered`
	// (not `sorted`, which is the same set in a different order).
	// -----------------------------------------------------------------------

	const stats = $derived.by(() => {
		const byStatus: Partial<Record<ReviewStatus, number>> = {};
		const byTier: Record<DetectionTier, number> = { '1': 0, '2': 0, '3': 0 };
		const byArticle: Record<string, number> = {};
		let autoCount = 0;
		let manualCount = 0;
		for (const d of filtered) {
			byStatus[d.review_status] = (byStatus[d.review_status] ?? 0) + 1;
			byTier[d.tier] = (byTier[d.tier] ?? 0) + 1;
			if (d.woo_article) {
				byArticle[d.woo_article] = (byArticle[d.woo_article] ?? 0) + 1;
			}
			if (isAutoSource(d.source)) autoCount++;
			else manualCount++;
		}
		return {
			total: filtered.length,
			byStatus,
			byTier,
			byArticle,
			autoCount,
			manualCount
		};
	});

	// -----------------------------------------------------------------------
	// Sort + filter UI handlers
	// -----------------------------------------------------------------------

	function toggleSort(key: SortKey) {
		if (sortKey === key) {
			sortDir = sortDir === 'asc' ? 'desc' : 'asc';
		} else {
			sortKey = key;
			sortDir = 'asc';
		}
	}

	function clearFilters() {
		filterTier = '';
		filterStatus = '';
		filterEntityType = '';
		filterArticle = '';
		filterSource = '';
		filterPage = '';
	}

	// -----------------------------------------------------------------------
	// Selection (batch-op multi-select)
	// -----------------------------------------------------------------------

	function toggleRow(id: string) {
		const next = new Set(selectedIds);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		selectedIds = next;
	}

	function isSelected(id: string): boolean {
		return selectedIds.has(id);
	}

	const allVisibleSelected = $derived(
		sorted.length > 0 && sorted.every((d) => selectedIds.has(d.id))
	);

	function toggleAllVisible() {
		if (allVisibleSelected) {
			const next = new Set(selectedIds);
			for (const d of sorted) next.delete(d.id);
			selectedIds = next;
		} else {
			const next = new Set(selectedIds);
			for (const d of sorted) next.add(d.id);
			selectedIds = next;
		}
	}

	function clearSelection() {
		selectedIds = new Set();
	}

	// -----------------------------------------------------------------------
	// Batch actions
	//
	// All actions go through the detection store's `review` / `remove`
	// methods so the in-memory list stays authoritative. We deliberately do
	// NOT push these onto the undo stack: the undo stack lives on the
	// review page and is scoped to the current review session; bulk log
	// actions happen outside that context and surfacing them as a mixed
	// undo history would make it easy to accidentally revert work from two
	// different screens. Bulk ops go through a confirmation dialog instead.
	// -----------------------------------------------------------------------

	function openBulkStatus(status: ReviewStatus) {
		pendingBulk = { kind: 'status', status, label: getReviewStatusLabel(status) };
	}

	function openBulkArticle(article: WooArticleCode) {
		if (!article) return;
		pendingBulk = { kind: 'article', article };
	}

	function openBulkDelete() {
		pendingBulk = { kind: 'delete' };
	}

	function cancelBulk() {
		pendingBulk = null;
	}

	/**
	 * Bulk delete targets only reviewer-authored rows (source `manual` or
	 * `search_redact`). The backend rejects deletes on auto detections with
	 * a 4xx, and the undo story for deleting auto detections is "flip to
	 * rejected", not "delete" — which belongs to the single-row review
	 * actions, not the log.
	 */
	const deletableSelectedIds = $derived.by(() => {
		const ids: string[] = [];
		for (const id of selectedIds) {
			const d = detectionStore.all.find((x) => x.id === id);
			if (d && (d.source === 'manual' || d.source === 'search_redact')) ids.push(id);
		}
		return ids;
	});

	async function confirmBulk() {
		if (!pendingBulk) return;
		bulkRunning = true;
		try {
			if (pendingBulk.kind === 'status') {
				const status = pendingBulk.status;
				for (const id of selectedIds) {
					await detectionStore.review(id, { review_status: status });
				}
			} else if (pendingBulk.kind === 'article') {
				const article = pendingBulk.article;
				for (const id of selectedIds) {
					await detectionStore.review(id, { woo_article: article });
				}
			} else if (pendingBulk.kind === 'delete') {
				for (const id of deletableSelectedIds) {
					await detectionStore.remove(id);
				}
			}
			clearSelection();
		} finally {
			bulkRunning = false;
			pendingBulk = null;
		}
	}

	// -----------------------------------------------------------------------
	// Single-row actions (from the expanded detail panel)
	// -----------------------------------------------------------------------

	async function rowAccept(id: string) {
		const det = detectionStore.all.find((d) => d.id === id);
		await detectionStore.review(id, {
			review_status: 'accepted',
			woo_article: det?.woo_article ?? undefined
		});
	}
	async function rowReject(id: string) {
		await detectionStore.review(id, { review_status: 'rejected' });
	}
	async function rowDefer(id: string) {
		await detectionStore.review(id, { review_status: 'deferred' });
	}
	async function rowReopen(id: string) {
		await detectionStore.review(id, { review_status: 'pending' });
	}

	// -----------------------------------------------------------------------
	// Navigation — "Bekijk in document" jumps back into the review screen
	// at the detection's page. The review page will pick up the
	// `?detection=` query param, select the row, and scroll the PDF.
	// -----------------------------------------------------------------------

	function viewInDocument(id: string) {
		goto(`/review/${docId}?detection=${id}`);
	}

	function formatDate(iso: string | null): string {
		if (!iso) return '—';
		try {
			return new Date(iso).toLocaleString('nl-NL', {
				year: 'numeric',
				month: '2-digit',
				day: '2-digit',
				hour: '2-digit',
				minute: '2-digit'
			});
		} catch {
			return iso;
		}
	}

	function sortIndicator(key: SortKey): string {
		if (sortKey !== key) return '';
		return sortDir === 'asc' ? '↑' : '↓';
	}

	const articleCodes = Object.keys(WOO_ARTICLES) as WooArticleCode[];
</script>

<svelte:head>
	<title>Lak-logboek — WOO Buddy</title>
</svelte:head>

<div class="flex h-full flex-col bg-gray-50">
	<!-- Header -->
	<div class="flex shrink-0 items-center gap-3 border-b border-gray-200 bg-white px-5 py-3">
		<a
			href="/review/{docId}"
			class="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm text-neutral hover:bg-gray-100 hover:text-gray-900"
			title="Terug naar review"
		>
			<ArrowLeft size={16} />
			<span>Terug naar review</span>
		</a>
		<div class="h-5 w-px bg-gray-200"></div>
		<div class="flex flex-col">
			<h1 class="text-sm font-semibold text-gray-900">Lak-logboek</h1>
			{#if reviewStore.document}
				<p class="text-xs text-neutral">{reviewStore.document.filename}</p>
			{/if}
		</div>
		<div class="ml-auto text-xs text-neutral">
			<!-- Client-first reminder — makes the missing "Passage" column legible. -->
			<span>Passages worden niet op de server opgeslagen. Gebruik <em>Bekijk</em> om de context in het document te zien.</span>
		</div>
	</div>

	{#if detectionStore.error}
		<div class="mx-5 mt-3">
			<Alert variant="danger">{detectionStore.error}</Alert>
		</div>
	{/if}

	<!-- Stats bar (filter-aware) -->
	<div class="flex flex-wrap items-center gap-2 border-b border-gray-200 bg-white px-5 py-3 text-xs">
		<div class="flex items-center gap-2 rounded-md border border-gray-200 bg-gray-50 px-3 py-1.5">
			<span class="font-semibold text-gray-900">{stats.total}</span>
			<span class="text-neutral">detecties</span>
			{#if hasFilters}
				<span class="ml-1 rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">gefilterd</span>
			{/if}
		</div>

		{#each REVIEW_STATUS_ORDER as status}
			{#if (stats.byStatus[status] ?? 0) > 0}
				<div class="flex items-center gap-1.5 rounded-md border border-gray-200 bg-white px-2.5 py-1.5">
					<span class="h-2 w-2 rounded-full {getReviewStatusBadgeClass(status).split(' ')[0]}"></span>
					<span class="text-neutral">{getReviewStatusLabel(status)}</span>
					<span class="font-semibold text-gray-900">{stats.byStatus[status] ?? 0}</span>
				</div>
			{/if}
		{/each}

		<div class="h-5 w-px bg-gray-200"></div>

		<div class="flex items-center gap-1.5 text-neutral">
			<span>Trap 1:</span><span class="font-semibold text-gray-900">{stats.byTier['1']}</span>
			<span>·</span>
			<span>Trap 2:</span><span class="font-semibold text-gray-900">{stats.byTier['2']}</span>
			<span>·</span>
			<span>Trap 3:</span><span class="font-semibold text-gray-900">{stats.byTier['3']}</span>
		</div>

		<div class="h-5 w-px bg-gray-200"></div>

		<div class="flex items-center gap-1.5 text-neutral">
			<span>Auto:</span><span class="font-semibold text-gray-900">{stats.autoCount}</span>
			<span>·</span>
			<span>Handmatig:</span><span class="font-semibold text-gray-900">{stats.manualCount}</span>
		</div>
	</div>

	<!-- Filter bar -->
	<div class="flex flex-wrap items-center gap-2 border-b border-gray-200 bg-white px-5 py-2 text-xs">
		<span class="font-medium text-neutral">Filters:</span>

		<sl-select
			size="small"
			placeholder="Alle trappen"
			value={filterTier}
			clearable
			onsl-change={(e: Event) => {
				filterTier = ((e.target as HTMLSelectElement).value || '') as DetectionTier | '';
			}}
		>
			{#each ['1', '2', '3'] as const as t}
				<sl-option value={t}>Trap {t} — {TIERS[t].label}</sl-option>
			{/each}
		</sl-select>

		<sl-select
			size="small"
			placeholder="Alle statussen"
			value={filterStatus}
			clearable
			onsl-change={(e: Event) => {
				filterStatus = ((e.target as HTMLSelectElement).value || '') as ReviewStatus | '';
			}}
		>
			{#each REVIEW_STATUS_ORDER as s}
				<sl-option value={s}>{REVIEW_STATUSES[s].label}</sl-option>
			{/each}
		</sl-select>

		<sl-select
			size="small"
			placeholder="Alle types"
			value={filterEntityType}
			clearable
			onsl-change={(e: Event) => {
				filterEntityType = ((e.target as HTMLSelectElement).value || '') as EntityType | '';
			}}
		>
			{#each ENTITY_TYPE_ORDER as t}
				<sl-option value={t}>{ENTITY_TYPES[t].label}</sl-option>
			{/each}
		</sl-select>

		<sl-select
			size="small"
			placeholder="Alle gronden"
			value={filterArticle}
			clearable
			onsl-change={(e: Event) => {
				filterArticle = ((e.target as HTMLSelectElement).value || '') as WooArticleCode | '';
			}}
		>
			{#each articleCodes as code}
				<sl-option value={code}>Art. {code}</sl-option>
			{/each}
		</sl-select>

		<sl-select
			size="small"
			placeholder="Alle bronnen"
			value={filterSource}
			clearable
			onsl-change={(e: Event) => {
				filterSource = ((e.target as HTMLSelectElement).value || '') as DetectionSource | '';
			}}
		>
			{#each Object.entries(DETECTION_SOURCES) as [value, info]}
				<sl-option value={value}>{info.label}</sl-option>
			{/each}
		</sl-select>

		<input
			type="number"
			min="1"
			placeholder="Pagina…"
			class="w-20 rounded border border-gray-300 bg-white px-2 py-1 text-xs"
			bind:value={filterPage}
		/>

		{#if hasFilters}
			<sl-button size="small" variant="text" onclick={clearFilters}>
				<span slot="prefix"><X size={12} /></span>
				Wis filters
			</sl-button>
		{/if}
	</div>

	<!-- Batch toolbar -->
	{#if selectedIds.size > 0}
		<div class="flex flex-wrap items-center gap-2 border-b border-primary/20 bg-primary/5 px-5 py-2 text-xs">
			<span class="font-semibold text-primary">
				{selectedIds.size} geselecteerd
			</span>
			<button
				type="button"
				class="text-neutral underline hover:text-gray-900"
				onclick={clearSelection}
			>
				selectie wissen
			</button>
			<div class="h-4 w-px bg-primary/20"></div>
			<span class="text-neutral">Status:</span>
			<sl-button size="small" onclick={() => openBulkStatus('accepted')}>
				<span slot="prefix"><Check size={12} /></span>
				Accepteren
			</sl-button>
			<sl-button size="small" onclick={() => openBulkStatus('rejected')}>
				<span slot="prefix"><Ban size={12} /></span>
				Afwijzen
			</sl-button>
			<sl-button size="small" onclick={() => openBulkStatus('deferred')}>
				<span slot="prefix"><Clock size={12} /></span>
				Uitstellen
			</sl-button>

			<div class="h-4 w-px bg-primary/20"></div>
			<span class="text-neutral">Grond:</span>
			<sl-select
				size="small"
				placeholder="Kies artikel…"
				value=""
				onsl-change={(e: Event) => {
					const val = (e.target as HTMLSelectElement).value as WooArticleCode;
					if (val) openBulkArticle(val);
				}}
			>
				{#each articleCodes as code}
					<sl-option value={code}>Art. {code}</sl-option>
				{/each}
			</sl-select>

			{#if deletableSelectedIds.length > 0}
				<div class="h-4 w-px bg-primary/20"></div>
				<sl-button size="small" variant="danger" onclick={openBulkDelete}>
					<span slot="prefix"><Trash2 size={12} /></span>
					Verwijderen ({deletableSelectedIds.length})
				</sl-button>
			{/if}
		</div>
	{/if}

	<!-- Table -->
	<div class="flex-1 overflow-auto">
		{#if detectionStore.loading && detectionStore.all.length === 0}
			<div class="flex h-full items-center justify-center">
				<sl-spinner style="font-size: 2rem; --indicator-color: var(--color-primary);"></sl-spinner>
			</div>
		{:else if sorted.length === 0}
			<div class="flex h-full flex-col items-center justify-center gap-2 text-center text-sm text-neutral">
				{#if detectionStore.all.length === 0}
					<p>Nog geen detecties voor dit document.</p>
				{:else}
					<p>Geen detecties die aan de huidige filters voldoen.</p>
					<button class="text-xs text-primary underline" onclick={clearFilters}>Wis filters</button>
				{/if}
			</div>
		{:else}
			<table class="w-full border-collapse text-xs">
				<thead class="sticky top-0 z-10 bg-white shadow-sm">
					<tr class="border-b border-gray-200 text-left text-[11px] uppercase tracking-wide text-neutral">
						<th class="w-10 px-3 py-2">
							<sl-checkbox
								size="small"
								checked={allVisibleSelected || undefined}
								onsl-change={toggleAllVisible}
							></sl-checkbox>
						</th>
						<th class="w-8 px-1 py-2"></th>
						<th class="w-12 cursor-pointer px-3 py-2 select-none" onclick={() => toggleSort('index')}>
							# {sortIndicator('index')}
						</th>
						<th class="w-16 cursor-pointer px-3 py-2 select-none" onclick={() => toggleSort('page')}>
							Pagina {sortIndicator('page')}
						</th>
						<th class="cursor-pointer px-3 py-2 select-none" onclick={() => toggleSort('entity_type')}>
							Type {sortIndicator('entity_type')}
						</th>
						<th class="w-16 cursor-pointer px-3 py-2 select-none" onclick={() => toggleSort('tier')}>
							Trap {sortIndicator('tier')}
						</th>
						<th class="w-24 cursor-pointer px-3 py-2 select-none" onclick={() => toggleSort('woo_article')}>
							Grond {sortIndicator('woo_article')}
						</th>
						<th class="w-32 cursor-pointer px-3 py-2 select-none" onclick={() => toggleSort('review_status')}>
							Status {sortIndicator('review_status')}
						</th>
						<th class="w-24 cursor-pointer px-3 py-2 select-none" onclick={() => toggleSort('source')}>
							Bron {sortIndicator('source')}
						</th>
						<th class="w-32 cursor-pointer px-3 py-2 select-none" onclick={() => toggleSort('reviewed_at')}>
							Beoordeeld {sortIndicator('reviewed_at')}
						</th>
						<th class="w-20 px-3 py-2"></th>
					</tr>
				</thead>
				<tbody>
					{#each sorted as d, i (d.id)}
						{@const expanded = expandedId === d.id}
						<tr
							class="border-b border-gray-100 bg-white hover:bg-gray-50"
							class:bg-primary-50={isSelected(d.id)}
							style={isSelected(d.id) ? 'background-color: rgb(239 246 255);' : ''}
						>
							<td class="px-3 py-1.5" onclick={(e) => e.stopPropagation()}>
								<sl-checkbox
									size="small"
									checked={isSelected(d.id) || undefined}
									onsl-change={() => toggleRow(d.id)}
								></sl-checkbox>
							</td>
							<td class="px-1 py-1.5">
								<button
									type="button"
									class="text-neutral hover:text-gray-900"
									title={expanded ? 'Inklappen' : 'Uitklappen'}
									onclick={() => (expandedId = expanded ? null : d.id)}
								>
									{#if expanded}
										<ChevronDown size={14} />
									{:else}
										<ChevronRight size={14} />
									{/if}
								</button>
							</td>
							<td class="px-3 py-1.5 text-neutral tabular-nums">{i + 1}</td>
							<td class="px-3 py-1.5 tabular-nums">
								{#if firstPage(d) >= 0}
									{firstPage(d) + 1}
								{:else}
									—
								{/if}
							</td>
							<td class="px-3 py-1.5">
								<span class="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium {getEntityTypeBadgeClass(d.entity_type)}">
									{getEntityTypeLabel(d.entity_type)}
								</span>
							</td>
							<td class="px-3 py-1.5">
								<span class="rounded border border-gray-200 bg-gray-50 px-1.5 py-0.5 text-[11px] font-medium text-gray-700">
									T{d.tier}
								</span>
							</td>
							<td class="px-3 py-1.5">
								{#if d.woo_article}
									<sl-tooltip content={getArticleLabel(d.woo_article)}>
										<span class="cursor-help font-mono text-[11px] text-gray-700">
											{d.woo_article}
										</span>
									</sl-tooltip>
								{:else}
									<span class="text-neutral">—</span>
								{/if}
							</td>
							<td class="px-3 py-1.5">
								<span class="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium {getReviewStatusBadgeClass(d.review_status)}">
									{getReviewStatusLabel(d.review_status)}
								</span>
							</td>
							<td class="px-3 py-1.5 text-neutral">{getSourceLabel(d.source)}</td>
							<td class="px-3 py-1.5 text-neutral">{formatDate(d.reviewed_at)}</td>
							<td class="px-3 py-1.5 text-right">
								<sl-tooltip content="Bekijk in document">
									<sl-button size="small" variant="text" onclick={() => viewInDocument(d.id)}>
										<Eye size={13} />
									</sl-button>
								</sl-tooltip>
							</td>
						</tr>
						{#if expanded}
							<tr class="border-b border-gray-200 bg-gray-50">
								<td></td>
								<td colspan="10" class="px-4 py-3">
									<div class="flex flex-col gap-3">
										<!-- Metadata grid -->
										<div class="grid grid-cols-2 gap-x-6 gap-y-1 text-[11px] sm:grid-cols-4">
											<div>
												<div class="text-neutral">Detection ID</div>
												<div class="font-mono text-[10px] text-gray-700">{d.id.slice(0, 8)}…</div>
											</div>
											<div>
												<div class="text-neutral">Zekerheid</div>
												<div class="tabular-nums text-gray-900">
													{(d.confidence * 100).toFixed(0)}% ({d.confidence_level ?? '—'})
												</div>
											</div>
											<div>
												<div class="text-neutral">Bboxes</div>
												<div class="text-gray-900">{d.bounding_boxes?.length ?? 0}</div>
											</div>
											<div>
												<div class="text-neutral">Reviewer</div>
												<div class="text-gray-900">{d.reviewer_id ?? '—'}</div>
											</div>
											{#if d.subject_role}
												<div>
													<div class="text-neutral">Rol</div>
													<div class="text-gray-900">{d.subject_role}</div>
												</div>
											{/if}
										</div>
										<!-- Motivation -->
										<div>
											<div class="text-[11px] text-neutral">Motivering</div>
											<div class="whitespace-pre-wrap rounded border border-gray-200 bg-white px-2 py-1.5 text-xs text-gray-800">
												{d.reasoning ?? 'Geen motivering vastgelegd.'}
											</div>
										</div>
										<!-- Row actions -->
										<div class="flex flex-wrap gap-2">
											<sl-button size="small" variant="primary" onclick={() => rowAccept(d.id)}>
												Accepteer
											</sl-button>
											<sl-button size="small" onclick={() => rowReject(d.id)}>
												Wijs af
											</sl-button>
											<sl-button size="small" onclick={() => rowDefer(d.id)}>
												Stel uit
											</sl-button>
											<sl-button size="small" variant="text" onclick={() => rowReopen(d.id)}>
												Heropenen
											</sl-button>
											<sl-button size="small" variant="text" onclick={() => viewInDocument(d.id)}>
												<span slot="prefix"><Eye size={13} /></span>
												Bekijk in document
											</sl-button>
										</div>
									</div>
								</td>
							</tr>
						{/if}
					{/each}
				</tbody>
			</table>
		{/if}
	</div>
</div>

<!-- Bulk confirmation dialog -->
<sl-dialog
	label="Bulk-actie bevestigen"
	open={pendingBulk !== null || undefined}
	onsl-request-close={(e: Event) => {
		// Don't let the user close the dialog mid-bulk-op — otherwise the
		// ongoing review calls would race with a fresh open.
		if (bulkRunning) {
			e.preventDefault();
			return;
		}
		pendingBulk = null;
	}}
>
	{#if pendingBulk?.kind === 'status'}
		<p class="text-sm">
			Status van <strong>{selectedIds.size}</strong> detecties wijzigen naar
			<strong>{pendingBulk.label}</strong>.
		</p>
	{:else if pendingBulk?.kind === 'article'}
		<p class="text-sm">
			Grond van <strong>{selectedIds.size}</strong> detecties wijzigen naar
			<strong>Art. {pendingBulk.article}</strong> — {WOO_ARTICLES[pendingBulk.article].ground}.
		</p>
	{:else if pendingBulk?.kind === 'delete'}
		<p class="text-sm">
			<strong>{deletableSelectedIds.length}</strong> handmatige detecties definitief verwijderen.
			Automatische detecties in de selectie worden overgeslagen — gebruik <em>Afwijzen</em> om die
			uit de lak te halen.
		</p>
	{/if}
	<p class="mt-2 text-xs text-neutral">Deze actie is niet opgenomen in de undo-geschiedenis van het reviewscherm.</p>

	<sl-button slot="footer" variant="default" onclick={cancelBulk} disabled={bulkRunning}>
		Annuleren
	</sl-button>
	<sl-button
		slot="footer"
		variant={pendingBulk?.kind === 'delete' ? 'danger' : 'primary'}
		onclick={confirmBulk}
		loading={bulkRunning || undefined}
		disabled={bulkRunning || undefined}
	>
		Bevestigen
	</sl-button>
</sl-dialog>
