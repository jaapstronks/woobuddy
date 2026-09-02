<script lang="ts">
	/**
	 * Thin, dependency-free progress bar for surfaces that are reachable
	 * from the SSR landing page (#68). It replaces `<sl-progress-bar>` in
	 * `ProgressSteps` and `ProviderPickerButtons`: those two imports were
	 * the only reason Lit and Shoelace ended up in the `/` bundle, which
	 * CLAUDE.md forbids. Do not import Shoelace here — the vitest gate in
	 * `src/routes/landing-no-shoelace.test.ts` walks the landing page's import
	 * graph and fails on the first `@shoelace-style` module it finds.
	 *
	 * `value` is 0..100; `null`/`undefined` renders an indeterminate bar.
	 */
	let {
		value = null,
		label = 'Bezig…'
	}: {
		value?: number | null;
		/** Accessible name; the bar is announced, the track is decorative. */
		label?: string;
	} = $props();

	const clamped = $derived(
		value == null ? null : Math.min(100, Math.max(0, Math.round(value)))
	);
</script>

<div
	class="progress-track"
	role="progressbar"
	aria-label={label}
	aria-valuemin={clamped == null ? undefined : 0}
	aria-valuemax={clamped == null ? undefined : 100}
	aria-valuenow={clamped ?? undefined}
>
	<div
		class="progress-fill"
		class:indeterminate={clamped == null}
		style:width={clamped == null ? undefined : `${clamped}%`}
	></div>
</div>

<style>
	.progress-track {
		position: relative;
		height: 4px;
		width: 100%;
		overflow: hidden;
		border-radius: 9999px;
		background: var(--color-primary-soft);
	}

	.progress-fill {
		height: 100%;
		border-radius: inherit;
		background: var(--color-primary);
		transition: width 200ms ease-out;
	}

	.progress-fill.indeterminate {
		position: absolute;
		inset-block: 0;
		width: 40%;
		animation: progress-slide 1.2s ease-in-out infinite;
	}

	@keyframes progress-slide {
		from {
			left: -40%;
		}
		to {
			left: 100%;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.progress-fill.indeterminate {
			animation-duration: 3s;
		}
	}
</style>
