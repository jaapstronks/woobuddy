<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		compact?: boolean;
		interactive?: boolean;
		class?: string;
		children: Snippet;
	}

	let { compact = false, interactive = false, class: extraClass = '', children }: Props = $props();
</script>

<div
	class="card {compact ? 'card--compact' : ''} {interactive ? 'card--interactive' : ''} {extraClass}"
>
	{@render children()}
</div>

<style>
	.card {
		border-radius: 0.75rem;
		border: 1px solid #e5e7eb;
		background: white;
		padding: 1.5rem;
	}

	.card--compact {
		border-radius: 0.5rem;
		padding: 0.75rem;
	}

	.card--interactive {
		transition: all 0.15s ease;
	}

	.card--interactive:hover {
		border-color: rgba(27, 79, 114, 0.3);
		box-shadow:
			0 4px 6px -1px rgba(0, 0, 0, 0.1),
			0 2px 4px -2px rgba(0, 0, 0, 0.1);
	}
</style>
