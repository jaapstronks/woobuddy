<script lang="ts">
	let { size = 'default' }: { size?: 'small' | 'default' | 'large' } = $props();

	const sizes = {
		small: { bar: 28, text: 'text-base' },
		default: { bar: 38, text: 'text-xl' },
		large: { bar: 52, text: 'text-3xl' }
	};

	const s = $derived(sizes[size]);
</script>

<a href="/" class="group flex items-center gap-2.5 no-underline">
	<svg
		width={s.bar}
		height={s.bar * 0.42}
		viewBox="0 0 38 16"
		xmlns="http://www.w3.org/2000/svg"
		aria-hidden="true"
	>
		<rect
			x="0"
			y="0"
			width="38"
			height="16"
			rx="1"
			fill="var(--color-ink)"
		/>
	</svg>
	<span class="font-serif {s.text} tracking-tight text-ink">
		WOO <span class="italic text-ink-soft">Buddy</span>
	</span>
</a>
