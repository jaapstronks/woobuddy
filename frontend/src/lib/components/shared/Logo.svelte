<script lang="ts">
	let { size = 'default' }: { size?: 'small' | 'default' | 'large' } = $props();

	const sizes = {
		small: { mark: 28, text: 'text-base' },
		default: { mark: 38, text: 'text-xl' },
		large: { mark: 52, text: 'text-3xl' }
	};

	const s = $derived(sizes[size]);
</script>

<a href="/" class="group flex items-center gap-2.5 no-underline">
	<img
		src="/woobuddy-logo.png"
		alt=""
		width={s.mark}
		height={s.mark}
		class="block shrink-0"
		aria-hidden="true"
	/>
	<span class="font-serif {s.text} tracking-tight text-ink">
		WOO <span class="italic text-ink-soft">Buddy</span>
	</span>
</a>
