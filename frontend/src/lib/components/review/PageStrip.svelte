<script lang="ts">
	import { pageStatusLabel, type PageReviewStatusValue } from './page-review-status';

	/**
	 * Page completeness chip strip (#10). A horizontally-scrolling row of
	 * numbered circles, one per page, showing per-page review status. The
	 * active page gets an outlined ring so the reviewer can find their
	 * place even in a long document.
	 */
	interface Props {
		totalPages: number;
		currentPage: number;
		/** Sparse map of page-number → status. Missing ⇒ unreviewed. */
		pageStatuses: Record<number, PageReviewStatusValue>;
		onPageChange: (page: number) => void;
	}

	let { totalPages, currentPage, pageStatuses, onPageChange }: Props = $props();

	function getPageStatus(page: number): PageReviewStatusValue {
		return pageStatuses[page] ?? 'unreviewed';
	}
</script>

<div
	class="page-strip flex items-center gap-1 overflow-x-auto border-b border-gray-200 bg-white px-4 py-2"
>
	{#each Array.from({ length: totalPages }, (_, i) => i) as p (p)}
		{@const st = getPageStatus(p)}
		<button
			type="button"
			class="page-chip"
			class:chip-unreviewed={st === 'unreviewed'}
			class:chip-in-progress={st === 'in_progress'}
			class:chip-complete={st === 'complete'}
			class:chip-flagged={st === 'flagged'}
			class:chip-current={p === currentPage}
			title={`Pagina ${p + 1} — ${pageStatusLabel(st)}`}
			onclick={() => onPageChange(p)}
		>
			{#if st === 'complete'}
				&#10003;
			{:else if st === 'flagged'}
				&#9873;
			{:else}
				{p + 1}
			{/if}
		</button>
	{/each}
</div>

<style>
	.page-strip {
		scrollbar-width: thin;
	}
	.page-chip {
		flex: 0 0 auto;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 1.75rem;
		height: 1.75rem;
		padding: 0 0.375rem;
		border-radius: 9999px;
		border: 1px solid #d1d5db;
		background: white;
		font-size: 0.7rem;
		font-weight: 500;
		color: #4b5563;
		transition:
			transform 120ms,
			box-shadow 120ms,
			background-color 120ms;
	}
	.page-chip:hover {
		transform: translateY(-1px);
	}
	.chip-unreviewed {
		background: white;
		color: #6b7280;
	}
	.chip-in-progress {
		background: #fef3c7;
		border-color: #f59e0b;
		color: #78350f;
	}
	.chip-complete {
		background: #10b981;
		border-color: #059669;
		color: white;
	}
	.chip-flagged {
		background: #fbbf24;
		border-color: #d97706;
		color: #78350f;
	}
	.chip-current {
		box-shadow: 0 0 0 2px var(--color-primary, #1b4f72);
	}
</style>
