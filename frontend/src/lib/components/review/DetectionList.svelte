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
		/**
		 * Sidebar scroll container. When provided, the selection effect
		 * centers the newly-selected card inside it. Fallback to
		 * `scrollIntoView` when omitted (tests, storybook).
		 */
		scrollContainer?: HTMLElement | null;
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
		onSameNameSweep,
		scrollContainer = null
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

	// Sort by reading order: page, then top-to-bottom (y0), then
	// left-to-right (x0). The sidebar should track the reviewer's eye as
	// they read the PDF — the top-bar filters (tier / status / type) take
	// care of "only show Trap 2" or "only pending" views, so grouping by
	// tier in the sidebar is redundant and hides the spatial relationship
	// between detections. Rows without a bbox sort to the end defensively
	// (every detection should have one, but the sort must be total).
	function readingOrderKey(det: Detection): [number, number, number] {
		const bbox = det.bounding_boxes?.[0];
		if (!bbox) return [Infinity, Infinity, Infinity];
		return [bbox.page, bbox.y0, bbox.x0];
	}

	const orderedDetections = $derived(
		[...detections].sort((a, b) => {
			const [ap, ay, ax] = readingOrderKey(a);
			const [bp, by, bx] = readingOrderKey(b);
			if (ap !== bp) return ap - bp;
			if (ay !== by) return ay - by;
			return ax - bx;
		})
	);

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

	// Scroll the selected sidebar card into the visible portion of the
	// sidebar scroll container.
	//
	// Two subtleties driving this implementation:
	//
	// 1. `PdfViewer` *also* stamps `data-detection-id="..."` onto its
	//    highlight-overlay elements (see PdfViewer.svelte), so a global
	//    `document.querySelector(...)` would match the PDF overlay first
	//    (earlier in DOM order) and miss the sidebar card entirely. We
	//    scope the lookup to this component's root via `bind:this`.
	//
	// 2. We avoid `Element.scrollIntoView` because the sidebar ancestor
	//    chain mixes `overflow: hidden` and `overflow: auto`, and the
	//    cross-container cascade is unreliable — it sometimes scrolls
	//    the `overflow: hidden` parent and moves children out of view.
	//    The parent passes its own scroller via the `scrollContainer`
	//    prop, and we compute the target scrollTop ourselves so the card
	//    lands centered.
	//
	// `requestAnimationFrame` defers the measurement until after the
	// selection-highlight DOM mutation has been painted, so
	// `getBoundingClientRect` sees the final layout.
	let rootEl: HTMLElement | null = $state(null);

	$effect(() => {
		if (!selectedId || !rootEl) return;
		const id = selectedId;
		const root = rootEl;
		const scroller = scrollContainer;
		requestAnimationFrame(() => {
			const el = root.querySelector<HTMLElement>(
				`[data-detection-id="${id}"]`
			);
			if (!el) return;
			if (!scroller) {
				// Fallback for tests / storybook where the parent does not
				// pass a scroll container.
				el.scrollIntoView({ behavior: 'smooth', block: 'center' });
				return;
			}
			const elRect = el.getBoundingClientRect();
			const scRect = scroller.getBoundingClientRect();
			// Offset of the card relative to the scroller's current scroll
			// origin, minus half the viewport so the card lands centered.
			const delta =
				elRect.top - scRect.top - scroller.clientHeight / 2 + elRect.height / 2;
			scroller.scrollTo({ top: scroller.scrollTop + delta, behavior: 'smooth' });
		});
	});
</script>

<!-- No `overflow-y-auto` here: the sidebar's `flex-1 overflow-y-auto`
     wrapper in +page.svelte is the actual scroll container. `bind:this`
     gives the selection effect a scoped root so `querySelector` can't
     accidentally match PdfViewer overlay elements (which also carry
     `data-detection-id`). -->
<div bind:this={rootEl} class="space-y-2">
	<!-- #20 — sweep-block chips. One per structure span that contains at
	     least one pending detection. Hoisted to the top of the flat list
	     because they are document-level actions that apply to a whole
	     block, not a single row. The chip count reflects *pending* rows
	     only — decisions the reviewer already made are skipped server-
	     side and must not appear in the count. -->
	{#if onSweepBlock}
		{@const sweepable = spanGroups.filter((g) => g.pendingDetections.length > 0)}
		{#if sweepable.length > 0}
			<div class="flex flex-wrap gap-1.5 pb-1">
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

	{#each orderedDetections as det (det.id)}
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
			{#if det.entity_type === 'area'}
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
			{:else if det.tier === '1'}
				<Tier1Card detection={det} onUnredact={onReject} onRedact={onAccept} />
			{:else if det.tier === '2'}
				<Tier2Card
					detection={det}
					sameNameCount={sameNameCount(det)}
					{onAccept}
					{onReject}
					{onChangeArticle}
					{onSetSubjectRole}
					{onSameNameSweep}
				/>
			{:else if det.tier === '3'}
				<Tier3Panel
					detection={det}
					onRedact={onRedactWithArticle}
					onKeep={onReject}
					{onDefer}
					{onReopen}
					{onSaveMotivation}
				/>
			{/if}
		</button>
	{/each}

	{#if detections.length === 0}
		<div class="flex h-32 items-center justify-center text-sm text-neutral">
			Geen detecties gevonden
		</div>
	{/if}
</div>
