<script module lang="ts">
	/**
	 * A vertical multi-step progress indicator used on the /try flow while a
	 * PDF is being extracted, registered, and analysed. Each step transitions:
	 *
	 *   empty circle  →  active indicator  →  checkmark
	 *
	 * The active step renders a Shoelace progress bar underneath the label.
	 * When `percent` is null the bar is indeterminate (e.g. server detection
	 * round-trip where we don't know how long it will take); when a number is
	 * supplied it switches to determinate mode (e.g. per-page text extraction).
	 */
	export type StepStatus = 'pending' | 'active' | 'done';

	export interface Step {
		id: string;
		label: string;
		detail?: string | null;
		status: StepStatus;
		/** 0..100 for determinate progress on the active step; null = indeterminate. */
		percent?: number | null;
	}
</script>

<script lang="ts">
	import '@shoelace-style/shoelace/dist/components/progress-bar/progress-bar.js';
	import { Check } from 'lucide-svelte';

	let { steps }: { steps: Step[] } = $props();
</script>

<ol class="flex flex-col gap-3">
	{#each steps as step (step.id)}
		<li class="flex items-start gap-3">
			<div
				class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[11px] font-medium transition-colors"
				class:border-border={step.status === 'pending'}
				class:text-ink-mute={step.status === 'pending'}
				class:border-primary={step.status === 'active'}
				class:bg-primary-soft={step.status === 'active'}
				class:text-primary={step.status === 'active'}
				class:bg-primary={step.status === 'done'}
				class:text-white={step.status === 'done'}
				class:border-transparent={step.status === 'done'}
				aria-hidden="true"
			>
				{#if step.status === 'done'}
					<Check size={14} strokeWidth={3} />
				{:else if step.status === 'active'}
					<span class="h-1.5 w-1.5 animate-pulse rounded-full bg-primary"></span>
				{/if}
			</div>
			<div class="flex-1 pt-0.5">
				<p
					class="text-sm transition-colors"
					class:text-ink-mute={step.status === 'pending'}
					class:font-medium={step.status !== 'pending'}
					class:text-ink={step.status === 'active'}
					class:text-ink-soft={step.status === 'done'}
				>
					{step.label}
				</p>
				{#if step.status === 'active'}
					<div class="mt-1.5">
						{#if step.percent == null}
							<sl-progress-bar indeterminate style="--height: 4px;"></sl-progress-bar>
						{:else}
							<sl-progress-bar value={step.percent} style="--height: 4px;"></sl-progress-bar>
						{/if}
						{#if step.detail}
							<p class="mt-1 text-xs text-ink-mute">{step.detail}</p>
						{/if}
					</div>
				{/if}
			</div>
		</li>
	{/each}
</ol>
