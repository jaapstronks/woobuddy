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
	class:toolbar-edit={mode === 'edit'}
>
	<div
		class="inline-flex rounded-md border border-gray-200 bg-gray-50 p-0.5"
		role="group"
		aria-label="Modus"
	>
		<button
			type="button"
			class="mode-btn"
			class:mode-btn-active={mode === 'review'}
			aria-pressed={mode === 'review'}
			title="Beoordelen (M)"
			onclick={() => onModeChange('review')}
		>
			Beoordelen
		</button>
		<button
			type="button"
			class="mode-btn"
			class:mode-btn-active={mode === 'edit'}
			aria-pressed={mode === 'edit'}
			title="Bewerken (M)"
			onclick={() => onModeChange('edit')}
		>
			Bewerken
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
	.toolbar-edit {
		box-shadow: inset 0 2px 0 0 var(--color-primary, #1b4f72);
	}
	.mode-btn {
		padding: 0.25rem 0.75rem;
		font-size: 0.75rem;
		font-weight: 500;
		color: #4b5563;
		border-radius: 0.25rem;
		transition:
			background-color 120ms,
			color 120ms;
	}
	.mode-btn:hover {
		background-color: rgba(0, 0, 0, 0.04);
	}
	.mode-btn-active {
		background-color: white;
		color: var(--color-primary, #1b4f72);
		box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
		/* #23 — brief background flash when the toggle flips. The
		   animation runs once each time the element acquires the
		   active class, then settles back to white. */
		animation: mode-toggle-pulse 220ms ease-out;
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
