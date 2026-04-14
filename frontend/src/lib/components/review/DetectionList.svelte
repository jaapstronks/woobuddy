<script lang="ts">
	import '@shoelace-style/shoelace/dist/components/button/button.js';

	import type { Detection, StructureSpan, SubjectRole, WooArticleCode } from '$lib/types';
	import { groupDetectionsBySpan, findSameNameDetections } from '$lib/utils/structure-matching';
	import Tier1Card from './Tier1Card.svelte';
	import Tier2Card from './Tier2Card.svelte';
	import Tier3Panel from './Tier3Panel.svelte';

	interface Props {
		detections: Detection[];
		selectedId: string | null;
		/**
		 * #18 — ids currently queued for merging. Visually highlighted in
		 * the sidebar so the reviewer can see what will be combined when
		 * they press "Samenvoegen". Always empty in review mode.
		 */
		multiSelectedIds?: string[];
		/**
		 * #20 — structure spans returned by the analyze pipeline for the
		 * current document. The sidebar uses them to render bulk-sweep
		 * chips on email header and signature block groups. Empty when
		 * analyze has not run this session (the affordance simply hides).
		 */
		structureSpans?: StructureSpan[];
		/** All detections across the document (pre-filter) — needed so the
		 *  same-name sweep link on a Tier 2 card can count *all* matching
		 *  occurrences, not only those visible under the current filter. */
		allDetections?: Detection[];
		onSelect: (id: string, modifier?: 'ctrl') => void;
		onAccept: (id: string) => void;
		onReject: (id: string) => void;
		onDefer: (id: string) => void;
		onReopen: (id: string) => void;
		onRedactWithArticle: (id: string, article: WooArticleCode) => void;
		onChangeArticle: (id: string, article: WooArticleCode) => void;
		onSetSubjectRole: (id: string, role: SubjectRole) => void;
		onSaveMotivation?: (id: string, text: string) => void;
		/**
		 * #20 — sweep a whole structure block (email header /
		 * signature block). The sidebar passes the span key so the
		 * handler can re-resolve the block from the spans store and
		 * build a `SweepBlockCommand` capturing current state.
		 */
		onSweepBlock?: (spanKey: string) => void;
		/**
		 * #20 — apply the selected detection's decision to every other
		 * occurrence of the same (normalized) name in the document.
		 */
		onSameNameSweep?: (detectionId: string) => void;
	}

	let {
		detections,
		selectedId,
		multiSelectedIds = [],
		structureSpans = [],
		allDetections,
		onSelect,
		onAccept,
		onReject,
		onDefer,
		onReopen,
		onRedactWithArticle,
		onChangeArticle,
		onSetSubjectRole,
		onSaveMotivation,
		onSweepBlock,
		onSameNameSweep
	}: Props = $props();

	// Ctrl/Cmd-click on a card queues the detection for merging (#18);
	// plain click keeps the existing single-select behavior. The DOM click
	// event fires on the <button> wrapper, so the `MouseEvent` is the
	// natural place to read the modifier state.
	function handleCardClick(e: MouseEvent, id: string) {
		if (e.ctrlKey || e.metaKey) {
			e.preventDefault();
			onSelect(id, 'ctrl');
			return;
		}
		onSelect(id);
	}

	function isMultiSelected(id: string): boolean {
		return multiSelectedIds.includes(id);
	}

	// Group detections by tier. Area redactions (#07) are pulled out into
	// their own group — they can ride on any Woo article (so any tier) but
	// share a common "manually drawn rectangle, no text" shape that the
	// tier-specific cards can't render cleanly.
	const grouped = $derived.by(() => {
		const areas = detections.filter((d) => d.entity_type === 'area');
		const rest = detections.filter((d) => d.entity_type !== 'area');
		const tier1 = rest.filter((d) => d.tier === '1');
		const tier2 = rest.filter((d) => d.tier === '2');
		const tier3 = rest.filter((d) => d.tier === '3');
		return { areas, tier1, tier2, tier3 };
	});

	// #20 — group visible detections by the structure span they fall inside
	// so the sidebar can render a "sweep this block" chip per email-header /
	// signature-block. We feed the *filtered* list in here: a chip whose
	// underlying detections are hidden by a filter would accept rows the
	// reviewer can't see, which is surprising. The count on the chip comes
	// from `pendingDetections` so decisions the reviewer already made are
	// not silently overwritten on click.
	const spanGroups = $derived.by(() => {
		if (!structureSpans || structureSpans.length === 0) return [];
		return groupDetectionsBySpan(detections, structureSpans);
	});

	// #20 — look up the same-name count for a detection against the full
	// (unfiltered) detection list. We need the unfiltered list because a
	// same-name sweep should apply to every occurrence in the document, not
	// just those currently matching the sidebar filter.
	function sameNameCount(det: Detection): number {
		if (det.entity_type !== 'persoon') return 0;
		const pool = allDetections ?? detections;
		return findSameNameDetections(det, pool).length;
	}

	// Map span.kind → the human Dutch label shown on the chip. The backend
	// emits `salutation` as well but we deliberately do not sweep those —
	// salutations are single names, not a block of related fields.
	function sweepBlockLabel(kind: string): string {
		if (kind === 'email_header') return 'Lak hele e-mailheader';
		if (kind === 'signature_block') return 'Lak handtekeningblok';
		return 'Lak blok';
	}

	// Lowest page number that contains *any* bbox for a detection — used for
	// the "pagina N" label on area detections. Guards against the (rare)
	// case where bounding_boxes is empty.
	function areaPageLabel(det: typeof detections[number]): string {
		const pages = (det.bounding_boxes ?? []).map((b) => b.page);
		if (pages.length === 0) return '—';
		return String(Math.min(...pages) + 1);
	}

	// Scroll selected card into view
	$effect(() => {
		if (selectedId) {
			const el = document.querySelector(`[data-detection-id="${selectedId}"]`);
			el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
		}
	});
</script>

<div class="space-y-4 overflow-y-auto">
	<!-- Handmatige gebieden (#07) -->
	{#if grouped.areas.length > 0}
		<div>
			<h3 class="mb-2 flex items-center gap-2 text-xs font-semibold uppercase text-neutral">
				<span class="h-2 w-2 rounded-full bg-gray-900"></span>
				Handmatig gebied ({grouped.areas.length})
			</h3>
			<div class="space-y-1">
				{#each grouped.areas as det (det.id)}
					<button
						data-detection-id={det.id}
						class="w-full text-left"
						class:ring-2={det.id === selectedId}
						class:ring-primary={det.id === selectedId}
						class:rounded-lg={det.id === selectedId}
						class:outline-2={isMultiSelected(det.id)}
						class:outline-warning={isMultiSelected(det.id)}
						onclick={(e: MouseEvent) => handleCardClick(e, det.id)}
					>
						<div class="rounded-lg border border-gray-200 bg-gray-50 p-3 transition-colors hover:bg-gray-100">
							<div class="flex items-start justify-between gap-2">
								<div class="min-w-0 flex-1">
									<div class="flex items-center gap-2">
										<span class="inline-block rounded bg-gray-900 px-1.5 py-0.5 text-xs text-white">
											gebied
										</span>
										{#if det.woo_article}
											<span class="text-xs text-neutral">Art. {det.woo_article}</span>
										{/if}
									</div>
									<p class="mt-1 text-sm text-gray-700">
										Handmatig gebied — pagina {areaPageLabel(det)}
									</p>
								</div>
								<sl-button
									size="small"
									variant="default"
									onclick={(e: Event) => {
										e.stopPropagation();
										onReject(det.id);
									}}
								>
									Ontlakken
								</sl-button>
							</div>
						</div>
					</button>
				{/each}
			</div>
		</div>
	{/if}

	<!-- Tier 1 -->
	{#if grouped.tier1.length > 0}
		<div>
			<h3 class="mb-2 flex items-center gap-2 text-xs font-semibold uppercase text-neutral">
				<span class="h-2 w-2 rounded-full bg-gray-700"></span>
				Trap 1 — Auto-gelakt ({grouped.tier1.length})
			</h3>
			<div class="space-y-1">
				{#each grouped.tier1 as det (det.id)}
					<button
						data-detection-id={det.id}
						class="w-full text-left"
						class:ring-2={det.id === selectedId}
						class:ring-primary={det.id === selectedId}
						class:rounded-lg={det.id === selectedId}
						class:outline-2={isMultiSelected(det.id)}
						class:outline-warning={isMultiSelected(det.id)}
						onclick={(e: MouseEvent) => handleCardClick(e, det.id)}
					>
						<Tier1Card detection={det} onUnredact={onReject} onRedact={onAccept} />
					</button>
				{/each}
			</div>
		</div>
	{/if}

	<!-- Tier 2 -->
	{#if grouped.tier2.length > 0}
		<div>
			<h3 class="mb-2 flex items-center gap-2 text-xs font-semibold uppercase text-neutral">
				<span class="h-2 w-2 rounded-full bg-warning"></span>
				Trap 2 — Beoordelen ({grouped.tier2.length})
			</h3>
			<!-- #20 — sweep-block chips. One per structure span that contains at
			     least one pending detection. The chip count reflects *pending*
			     rows only — decisions the reviewer already made are skipped
			     server-side and must not appear in the count, otherwise the
			     reviewer expects N accepts and gets N-K. -->
			{#if onSweepBlock}
				{@const sweepable = spanGroups.filter((g) => g.pendingDetections.length > 0)}
				{#if sweepable.length > 0}
					<div class="mb-2 flex flex-wrap gap-1.5">
						{#each sweepable as group (group.key)}
							<sl-button
								size="small"
								variant="warning"
								onclick={(e: Event) => {
									e.stopPropagation();
									onSweepBlock?.(group.key);
								}}
							>
								{sweepBlockLabel(group.span.kind)} ({group.pendingDetections.length})
							</sl-button>
						{/each}
					</div>
				{/if}
			{/if}
			<div class="space-y-2">
				{#each grouped.tier2 as det (det.id)}
					<button
						data-detection-id={det.id}
						class="w-full text-left"
						class:ring-2={det.id === selectedId}
						class:ring-primary={det.id === selectedId}
						class:rounded-lg={det.id === selectedId}
						class:outline-2={isMultiSelected(det.id)}
						class:outline-warning={isMultiSelected(det.id)}
						onclick={(e: MouseEvent) => handleCardClick(e, det.id)}
					>
						<Tier2Card
							detection={det}
							sameNameCount={sameNameCount(det)}
							{onAccept}
							{onReject}
							{onChangeArticle}
							{onSetSubjectRole}
							{onSameNameSweep}
						/>
					</button>
				{/each}
			</div>
		</div>
	{/if}

	<!-- Tier 3 -->
	{#if grouped.tier3.length > 0}
		<div>
			<h3 class="mb-2 flex items-center gap-2 text-xs font-semibold uppercase text-neutral">
				<span class="h-2 w-2 rounded-full bg-primary"></span>
				Trap 3 — Analyse ({grouped.tier3.length})
			</h3>
			<div class="space-y-3">
				{#each grouped.tier3 as det (det.id)}
					<button
						data-detection-id={det.id}
						class="w-full text-left"
						class:ring-2={det.id === selectedId}
						class:ring-primary={det.id === selectedId}
						class:rounded-lg={det.id === selectedId}
						class:outline-2={isMultiSelected(det.id)}
						class:outline-warning={isMultiSelected(det.id)}
						onclick={(e: MouseEvent) => handleCardClick(e, det.id)}
					>
						<Tier3Panel
							detection={det}
							onRedact={onRedactWithArticle}
							onKeep={onReject}
							{onDefer}
							{onReopen}
							{onSaveMotivation}
						/>
					</button>
				{/each}
			</div>
		</div>
	{/if}

	{#if detections.length === 0}
		<div class="flex h-32 items-center justify-center text-sm text-neutral">
			Geen detecties gevonden
		</div>
	{/if}
</div>
