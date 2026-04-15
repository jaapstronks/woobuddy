<script lang="ts">
	import type { PageReviewStatusValue } from './page-review-status';

	/**
	 * Floating per-page completeness actions (#10). Anchored to the top-right
	 * of the rendered page so it follows zoom and stays out of the bottom
	 * where pagination controls live. Kept small so it doesn't cover document
	 * content; the page strip is the primary overview.
	 */
	interface Props {
		currentPage: number;
		currentPageStatus: PageReviewStatusValue;
		onMarkPageReviewed?: (page: number) => void;
		onFlagPage?: (page: number) => void;
	}

	let { currentPage, currentPageStatus, onMarkPageReviewed, onFlagPage }: Props = $props();
</script>

<div class="page-review-actions">
	{#if currentPageStatus === 'complete'}
		<button
			type="button"
			class="page-action-btn page-action-done"
			title="Beoordeling ongedaan maken"
			onclick={() => onMarkPageReviewed?.(currentPage)}
		>
			&#10003; Beoordeeld
		</button>
	{:else}
		<button
			type="button"
			class="page-action-btn page-action-mark"
			title="Pagina beoordeeld (P)"
			onclick={() => onMarkPageReviewed?.(currentPage)}
		>
			Pagina beoordeeld
		</button>
	{/if}
	<button
		type="button"
		class="page-action-btn"
		class:page-action-flagged={currentPageStatus === 'flagged'}
		title="Later terugkomen (F)"
		onclick={() => onFlagPage?.(currentPage)}
	>
		&#9873;
	</button>
</div>

<style>
	.page-review-actions {
		position: absolute;
		top: 0.5rem;
		right: 0.5rem;
		display: flex;
		gap: 0.25rem;
		z-index: 4;
	}
	.page-action-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		padding: 0.3rem 0.6rem;
		border-radius: 9999px;
		border: 1px solid rgba(0, 0, 0, 0.08);
		background: rgba(255, 255, 255, 0.92);
		backdrop-filter: blur(4px);
		font-size: 0.75rem;
		font-weight: 500;
		color: #374151;
		box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
		cursor: pointer;
		transition:
			background-color 120ms,
			transform 120ms;
	}
	.page-action-btn:hover {
		background: white;
		transform: translateY(-1px);
	}
	.page-action-mark:hover {
		background: #ecfdf5;
		color: #065f46;
		border-color: #10b981;
	}
	.page-action-done {
		background: #10b981;
		color: white;
		border-color: #059669;
	}
	.page-action-done:hover {
		background: #059669;
	}
	.page-action-flagged {
		background: #fbbf24;
		color: #78350f;
		border-color: #d97706;
	}
</style>
