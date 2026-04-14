<script lang="ts">
	import '@shoelace-style/shoelace/dist/components/button/button.js';
	import '@shoelace-style/shoelace/dist/components/badge/badge.js';
	import '@shoelace-style/shoelace/dist/components/select/select.js';
	import '@shoelace-style/shoelace/dist/components/option/option.js';
	import '@shoelace-style/shoelace/dist/components/button-group/button-group.js';

	import type { Detection, EntityType, SubjectRole, WooArticleCode } from '$lib/types';
	import { CONFIDENCE_LABELS, CONFIDENCE_COLORS } from '$lib/utils/confidence';
	import { confidenceToLevel } from '$lib/utils/tiers';
	import { WOO_ARTICLES } from '$lib/utils/woo-articles';

	interface Props {
		detection: Detection;
		/**
		 * #20 — total number of detections in the document that normalize
		 * to the same name as this one (including this detection itself).
		 * Rendered when >= 2 as a "sweep all N" link. Computed by the
		 * parent against the unfiltered detection list so the count
		 * reflects the whole document, not just the current filter.
		 */
		sameNameCount?: number;
		onAccept: (id: string) => void;
		onReject: (id: string) => void;
		onChangeArticle: (id: string, article: WooArticleCode) => void;
		onSetSubjectRole: (id: string, role: SubjectRole) => void;
		/**
		 * #20 — apply the decision the reviewer is about to make (accept
		 * or reject) to every other occurrence of the same name. Optional
		 * because the callback is only wired on the review page, not in
		 * Tier2Card unit tests.
		 */
		onSameNameSweep?: (id: string) => void;
	}

	let {
		detection,
		sameNameCount = 0,
		onAccept,
		onReject,
		onChangeArticle,
		onSetSubjectRole,
		onSameNameSweep
	}: Props = $props();

	const isPending = $derived(detection.review_status === 'pending');
	const isAccepted = $derived(
		detection.review_status === 'accepted' || detection.review_status === 'auto_accepted'
	);
	const isRejected = $derived(detection.review_status === 'rejected');
	const isPropagated = $derived(!!detection.propagated_from);
	const article = $derived(detection.woo_article ? WOO_ARTICLES[detection.woo_article] : null);

	const confidenceLevel = $derived(confidenceToLevel(detection.confidence));
	const confidenceLabel = $derived(CONFIDENCE_LABELS[confidenceLevel]);
	const confidenceColor = $derived(CONFIDENCE_COLORS[confidenceLevel]);

	// Role chips are meaningful only for person-like detections. BSN/IBAN/etc.
	// are always personal data regardless of who the subject is. They are
	// now a follow-up question on the *rejected* path only: "je hebt
	// 'niet lakken' gekozen — waarom?". The pending card never shows them,
	// and classification no longer flips review_status as a side-effect.
	const PERSON_ENTITY_TYPES: EntityType[] = ['persoon', 'adres', 'telefoonnummer', 'email'];
	const showRoleChips = $derived(PERSON_ENTITY_TYPES.includes(detection.entity_type));

	// Tier 2 articles the picker exposes — same filter idea as Tier3Panel.
	const TIER2_ARTICLES = Object.values(WOO_ARTICLES).filter((a) => a.tier === '2');

	// Entity type badge colors
	const entityColors: Record<string, string> = {
		persoon: 'bg-primary/10 text-primary',
		adres: 'bg-purple-100 text-purple-700',
		datum: 'bg-gray-100 text-gray-600',
		organisatie: 'bg-blue-100 text-blue-600',
		gezondheid: 'bg-red-100 text-red-700'
	};
	const badgeClass = $derived(entityColors[detection.entity_type] ?? 'bg-gray-100 text-gray-600');

	// When the detection reasoning credits the Meertens Instituut
	// (Nederlandse Voornamenbank), split it into three parts so we
	// can render "Meertens Instituut" as a link back to the NVB. This
	// satisfies the Voornamenbank attribution requirement — see
	// `THIRD_PARTY_LICENSES.md` and `backend/app/data/sources/README.md`.
	const MEERTENS_LABEL = 'Meertens Instituut';
	const MEERTENS_URL = 'https://www.meertens.knaw.nl/nvb';
	// The Tier 2 suggestion text used to end with a "Classificatie nodig"
	// sentence asking the reviewer to pick a role upfront. Classification
	// is now a post-"Niet lakken" follow-up so the hint is always out of
	// place — strip it unconditionally.
	const CLASSIFICATION_HINT = 'Classificatie nodig';
	const reasoningText = $derived.by(() => {
		const raw = detection.reasoning ?? '';
		if (!raw) return '';
		const idx = raw.indexOf(CLASSIFICATION_HINT);
		return idx === -1 ? raw : raw.slice(0, idx).trimEnd();
	});
	const reasoningParts = $derived.by(() => {
		const reasoning = reasoningText;
		const idx = reasoning.indexOf(MEERTENS_LABEL);
		if (idx === -1) return null;
		return {
			before: reasoning.slice(0, idx),
			label: MEERTENS_LABEL,
			after: reasoning.slice(idx + MEERTENS_LABEL.length)
		};
	});

	function handleArticleChange(e: Event) {
		const target = e.target as HTMLSelectElement & { value: string };
		const next = target.value as WooArticleCode;
		if (!next || next === detection.woo_article) return;
		onChangeArticle(detection.id, next);
	}

	function handleRoleClick(role: SubjectRole, e: Event) {
		e.stopPropagation();
		if (detection.subject_role === role) return;
		onSetSubjectRole(detection.id, role);
	}
</script>

<div
	class="rounded-lg border p-3 transition-colors"
	class:border-warning={isPending}
	class:bg-amber-50={isPending}
	class:border-success={isAccepted}
	class:bg-green-50={isAccepted}
	class:border-gray-200={isRejected}
	class:bg-gray-50={isRejected}
>
	<!-- Header: entity type + article picker + confidence -->
	<div class="flex items-center gap-2 flex-wrap">
		<span class="inline-block rounded px-1.5 py-0.5 text-xs font-medium {badgeClass}">
			{detection.entity_type}
		</span>
		{#if article}
			<sl-badge variant="primary" pill>{detection.woo_article}</sl-badge>
		{/if}
		<span
			class="ml-auto rounded px-1.5 py-0.5 text-xs"
			style="color: {confidenceColor}"
		>
			{confidenceLabel}
		</span>
	</div>

	<!-- Entity text — visible in every state. On accepted, styled as a black
	     box with white text so the "this will be blacked out on export" mental
	     model is obvious. Falls back to a placeholder when entity_text could
	     not be resolved from the client-side extraction. -->
	{#if detection.entity_text}
		<p class="mt-2 rounded bg-white p-2 font-mono text-sm leading-relaxed">
			{#if isAccepted}
				<mark class="rounded bg-black px-1 text-white">{detection.entity_text}</mark>
			{:else if isRejected}
				<span class="text-gray-700">{detection.entity_text}</span>
			{:else}
				<mark class="rounded bg-warning/30 px-0.5">{detection.entity_text}</mark>
			{/if}
		</p>
	{:else}
		<p class="mt-2 rounded bg-white p-2 font-mono text-xs italic text-neutral">
			— tekst niet beschikbaar —
		</p>
	{/if}

	<!-- Reasoning -->
	{#if reasoningText}
		<p class="mt-2 text-xs leading-relaxed text-neutral">
			{#if reasoningParts}
				{reasoningParts.before}<a
					href={MEERTENS_URL}
					target="_blank"
					rel="noopener noreferrer"
					class="text-primary underline"
				>{reasoningParts.label}</a>{reasoningParts.after}
			{:else}
				{reasoningText}
			{/if}
		</p>
	{/if}

	<!-- Propagation note -->
	{#if isPropagated}
		<p class="mt-1 text-xs italic text-neutral">
			Gepropageerd vanuit eerder besluit
		</p>
	{/if}

	<!-- Context-sensitive detail block.
	     The card is conceptually a two-step form:
	       1. Do we redact? (Lakken / Niet lakken)
	       2a. If yes → on what Woo-grond?
	       2b. If no  → why not? (classificatie)
	     The detail block reflects step 2. In the pending state we preview
	     the suggested Woo-grond so the reviewer can see (and adjust) the
	     ground the suggestion is based on before committing. Once the
	     reviewer has chosen, the block switches to match the chosen path:
	     the Woo-grond picker stays active on the Lakken path, the
	     classification chips appear on the Niet-lakken path. Woo-grond and
	     classification are never shown together — they answer mutually
	     exclusive questions. -->
	{#if isRejected && showRoleChips}
		<!-- Niet lakken → reason. Burger is deliberately omitted: if the
		     subject is an ordinary citizen, the correct action is to
		     redact, not to classify + keep visible. -->
		<div class="mt-3">
			<div class="mb-1 text-[11px] font-medium text-gray-700">Reden om niet te lakken</div>
			<sl-button-group label="Reden om niet te lakken">
				<sl-button
					size="small"
					variant={detection.subject_role === 'ambtenaar' ? 'primary' : 'default'}
					onclick={(e: Event) => handleRoleClick('ambtenaar', e)}
				>
					Ambtenaar
				</sl-button>
				<sl-button
					size="small"
					variant={detection.subject_role === 'publiek_functionaris' ? 'primary' : 'default'}
					onclick={(e: Event) => handleRoleClick('publiek_functionaris', e)}
				>
					Publiek functionaris
				</sl-button>
			</sl-button-group>
		</div>
	{:else if detection.woo_article}
		<!-- Pending or Accepted → Woo-grond picker. The label shifts to
		     reflect the current state: in pending it's the suggested
		     ground, in accepted it's the active ground. -->
		<div class="mt-3">
			<label class="mb-1 block text-[11px] font-medium text-gray-700" for={`article-${detection.id}`}>
				{#if isAccepted}
					Op welke grond
				{:else}
					Voorgestelde grond
				{/if}
			</label>
			<sl-select
				id={`article-${detection.id}`}
				size="small"
				value={detection.woo_article}
				onsl-change={handleArticleChange}
				onclick={(e: Event) => e.stopPropagation()}
			>
				{#each TIER2_ARTICLES as opt (opt.code)}
					<sl-option value={opt.code}>{opt.code} — {opt.ground}</sl-option>
				{/each}
			</sl-select>
		</div>
	{/if}

	<!-- #20 — same-name sweep link. Visible only when this is a persoon
	     detection still awaiting a decision AND the document contains at
	     least one other occurrence of the same (normalized) name. Clicking
	     applies the reviewer's decision — captured by the parent as the
	     next status set on *this* card — to every other matching row. -->
	{#if isPending && detection.entity_type === 'persoon' && detection.entity_text && sameNameCount >= 2 && onSameNameSweep}
		<div class="mt-2 text-xs text-neutral">
			<button
				type="button"
				class="text-primary underline hover:text-primary/80"
				onclick={(e: Event) => {
					e.stopPropagation();
					onSameNameSweep?.(detection.id);
				}}
			>
				Pas toe op alle {sameNameCount} voorkomens van '{detection.entity_text}'
			</button>
		</div>
	{/if}

	<!-- Action row: varies by state. Pending shows the primary accept/reject
	     pair; accepted shows a "gelakt" badge plus an Ontlakken button;
	     rejected shows the inverse with a "Toch lakken" shortcut. -->
	{#if isPending}
		<div class="mt-3 flex items-center gap-2">
			<sl-button variant="danger" class="flex-1" onclick={() => onAccept(detection.id)}>
				Lakken
			</sl-button>
			<sl-button variant="success" outline class="flex-1" onclick={() => onReject(detection.id)}>
				Niet lakken
			</sl-button>
		</div>
	{:else if isAccepted}
		<div class="mt-3 flex items-center justify-between gap-2">
			<sl-badge variant="danger">Gelakt</sl-badge>
			<sl-button
				size="small"
				variant="default"
				onclick={(e: Event) => {
					e.stopPropagation();
					onReject(detection.id);
				}}
			>
				Ontlakken
			</sl-button>
		</div>
	{:else if isRejected}
		<div class="mt-3 flex items-center justify-between gap-2">
			<span class="text-xs text-success font-medium">Zichtbaar gehouden</span>
			<sl-button
				size="small"
				variant="default"
				onclick={(e: Event) => {
					e.stopPropagation();
					onAccept(detection.id);
				}}
			>
				Toch lakken
			</sl-button>
		</div>
	{/if}
</div>
