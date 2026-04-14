<script lang="ts">
	// Skeleton layout for the review screen, shown while the document and
	// detections are still loading. Matches the real layout — PDF page on
	// the left, detection cards on the right — so the transition to the
	// live UI does not shift anything around. The shimmer animation is
	// scoped to this component (see the style block below) so it does not
	// leak into other gray rectangles across the app. prefers-reduced-motion
	// disables it.
	const cardKeys = [0, 1, 2, 3];
</script>

<div class="flex min-h-0 flex-1" aria-busy="true" aria-live="polite">
	<span class="sr-only">Document en detecties worden geladen…</span>

	<!-- Skeleton PDF page -->
	<div class="flex flex-1 items-start justify-center overflow-hidden bg-gray-100 p-4">
		<div class="shimmer flex h-[80vh] w-full max-w-2xl flex-col gap-3 rounded border border-gray-200 bg-white p-8 shadow-sm">
			<div class="h-6 w-2/3 rounded bg-gray-200"></div>
			<div class="h-4 w-5/6 rounded bg-gray-200"></div>
			<div class="h-4 w-4/6 rounded bg-gray-200"></div>
			<div class="mt-3 h-4 w-5/6 rounded bg-gray-200"></div>
			<div class="h-4 w-3/6 rounded bg-gray-200"></div>
			<div class="h-4 w-4/6 rounded bg-gray-200"></div>
			<div class="mt-3 h-4 w-5/6 rounded bg-gray-200"></div>
			<div class="h-4 w-2/6 rounded bg-gray-200"></div>
			<div class="h-4 w-5/6 rounded bg-gray-200"></div>
			<div class="mt-3 h-4 w-4/6 rounded bg-gray-200"></div>
			<div class="h-4 w-5/6 rounded bg-gray-200"></div>
			<div class="h-4 w-3/6 rounded bg-gray-200"></div>
		</div>
	</div>

	<!-- Skeleton detection cards -->
	<div class="hidden w-96 shrink-0 flex-col gap-3 border-l border-gray-200 bg-gray-50/80 p-4 md:flex">
		{#each cardKeys as key (key)}
			<div class="shimmer rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
				<div class="flex items-center gap-2">
					<div class="h-4 w-14 rounded bg-gray-200"></div>
					<div class="h-4 w-20 rounded bg-gray-200"></div>
				</div>
				<div class="mt-3 h-5 w-3/4 rounded bg-gray-200"></div>
				<div class="mt-2 h-3 w-1/2 rounded bg-gray-200"></div>
				<div class="mt-4 flex gap-2">
					<div class="h-7 w-16 rounded bg-gray-200"></div>
					<div class="h-7 w-16 rounded bg-gray-200"></div>
				</div>
			</div>
		{/each}
	</div>
</div>

<style>
	.shimmer {
		position: relative;
		overflow: hidden;
	}
	.shimmer::after {
		content: "";
		position: absolute;
		inset: 0;
		background: linear-gradient(
			90deg,
			transparent 0%,
			rgba(255, 255, 255, 0.55) 50%,
			transparent 100%
		);
		transform: translateX(-100%);
		animation: shimmer 1.6s ease-in-out infinite;
		pointer-events: none;
	}
	@keyframes shimmer {
		100% {
			transform: translateX(100%);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.shimmer::after {
			animation: none;
			display: none;
		}
	}
</style>
