<script lang="ts">
	import type { ReviewMode } from '$lib/stores/review.svelte';
	import type { PageReviewStatusValue } from './page-review-status';

	interface Props {
		mode: ReviewMode;
		currentPage: number;
		totalPages: number;
		currentPageStatus: PageReviewStatusValue;
		onModeChange: (mode: ReviewMode) => void;
		onPageChange: (page: number) => void;
	}

	let { mode, currentPage, totalPages, currentPageStatus, onModeChange, onPageChange }: Props =
		$props();
</script>

<div
	class="sticky top-0 z-10 flex items-center justify-between gap-3 border-b bg-white/95 px-4 py-2 backdrop-blur-sm"
>
	<div class="mode-toggle" role="group" aria-label="Modus">
		<button
			type="button"
			class="mode-btn"
			class:mode-btn-active={mode === 'review'}
			aria-pressed={mode === 'review'}
			title="Beoordelen — klik op een suggestie om te accepteren of af te wijzen. Sleep over tekst om handmatig te lakken. (M)"
			onclick={() => onModeChange('review')}
		>
			<svg
				class="mode-icon"
				viewBox="0 0 20 20"
				fill="none"
				stroke="currentColor"
				stroke-width="1.8"
				aria-hidden="true"
			>
				<path
					d="M1.5 10s3-6 8.5-6 8.5 6 8.5 6-3 6-8.5 6S1.5 10 1.5 10z"
					stroke-linecap="round"
					stroke-linejoin="round"
				/>
				<circle cx="10" cy="10" r="2.5" />
			</svg>
			<span>Beoordelen</span>
			<kbd class="mode-kbd" aria-hidden="true">M</kbd>
		</button>
		<button
			type="button"
			class="mode-btn"
			class:mode-btn-active={mode === 'edit'}
			aria-pressed={mode === 'edit'}
			title="Bewerken — klik op een bestaande markering om de grens aan te passen. Sleep over tekst om handmatig te lakken. (M)"
			onclick={() => onModeChange('edit')}
		>
			<svg
				class="mode-icon"
				viewBox="0 0 20 20"
				fill="none"
				stroke="currentColor"
				stroke-width="1.8"
				aria-hidden="true"
			>
				<path
					d="M3 14.5V17h2.5l8.2-8.2-2.5-2.5L3 14.5z"
					stroke-linecap="round"
					stroke-linejoin="round"
				/>
				<path d="M12.3 5.3l2.5 2.5 1.6-1.6a1.2 1.2 0 0 0 0-1.7l-.8-.8a1.2 1.2 0 0 0-1.7 0l-1.6 1.6z" />
			</svg>
			<span>Bewerken</span>
			<kbd class="mode-kbd" aria-hidden="true">M</kbd>
		</button>
	</div>

	<div class="flex items-center gap-3">
		<button
			class="rounded px-2 py-1 text-sm hover:bg-gray-100 disabled:opacity-40"
			disabled={currentPage <= 0}
			onclick={() => onPageChange(currentPage - 1)}
		>
			&larr; Vorige
		</button>
		<span class="flex items-center gap-1.5 text-sm text-neutral">
			<!-- Inline indicator beside the page counter so the reviewer
			     always sees the current page's status, regardless of
			     whether the page strip is scrolled into view. -->
			<span
				class="page-status-dot"
				class:status-unreviewed={currentPageStatus === 'unreviewed'}
				class:status-in-progress={currentPageStatus === 'in_progress'}
				class:status-complete={currentPageStatus === 'complete'}
				class:status-flagged={currentPageStatus === 'flagged'}
				aria-hidden="true"
			></span>
			{currentPage + 1} / {totalPages > 0 ? totalPages : '...'}
		</span>
		<button
			class="rounded px-2 py-1 text-sm hover:bg-gray-100 disabled:opacity-40"
			disabled={totalPages === 0 || currentPage >= totalPages - 1}
			onclick={() => onPageChange(currentPage + 1)}
		>
			Volgende &rarr;
		</button>
	</div>
</div>

<style>
	/* Segmented mode toggle. The previous version was a subtle white-on-
	   white pill that reviewers reported couldn't be told apart from its
	   inactive sibling. This rebuild leans on three cues in parallel —
	   filled background + icon + visible `M` kbd hint — so the active mode
	   is unambiguous even at a glance. */
	.mode-toggle {
		display: inline-flex;
		gap: 0.25rem;
		padding: 0.25rem;
		border: 1px solid #e5e7eb;
		border-radius: 0.5rem;
		background: #f9fafb;
	}
	.mode-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.35rem 0.7rem;
		font-size: 0.8rem;
		font-weight: 500;
		color: #4b5563;
		background: transparent;
		border: 1px solid transparent;
		border-radius: 0.35rem;
		cursor: pointer;
		transition:
			background-color 120ms,
			color 120ms,
			border-color 120ms,
			box-shadow 120ms;
	}
	.mode-btn:hover:not(.mode-btn-active) {
		background-color: rgba(0, 0, 0, 0.04);
		color: #1f2937;
	}
	.mode-btn-active {
		background-color: var(--color-primary, #1b4f72);
		color: white;
		border-color: var(--color-primary, #1b4f72);
		box-shadow:
			0 1px 2px rgba(0, 0, 0, 0.12),
			0 0 0 1px rgba(27, 79, 114, 0.25);
		animation: mode-toggle-pulse 220ms ease-out;
	}
	.mode-icon {
		width: 1rem;
		height: 1rem;
		flex-shrink: 0;
	}
	.mode-kbd {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 1.1rem;
		padding: 0 0.25rem;
		font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
		font-size: 0.65rem;
		font-weight: 600;
		line-height: 1.1rem;
		border-radius: 0.2rem;
		background: rgba(0, 0, 0, 0.08);
		color: inherit;
		opacity: 0.75;
	}
	.mode-btn-active .mode-kbd {
		background: rgba(255, 255, 255, 0.22);
		opacity: 0.95;
	}
	@media (prefers-reduced-motion: reduce) {
		.mode-btn,
		.mode-btn-active {
			animation: none;
			transition: none;
		}
	}

	/* Inline dot beside the toolbar's page counter — mirrors the chip
	   colors so the reviewer recognises the state language. */
	.page-status-dot {
		display: inline-block;
		width: 0.6rem;
		height: 0.6rem;
		border-radius: 9999px;
		border: 1px solid #d1d5db;
		background: white;
	}
	.page-status-dot.status-in-progress {
		background: #f59e0b;
		border-color: #b45309;
	}
	.page-status-dot.status-complete {
		background: #10b981;
		border-color: #059669;
	}
	.page-status-dot.status-flagged {
		background: #fbbf24;
		border-color: #d97706;
	}
</style>
