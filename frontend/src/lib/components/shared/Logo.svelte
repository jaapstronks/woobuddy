<script lang="ts">
	import { ShieldCheck } from 'lucide-svelte';

	let { size = 'default' }: { size?: 'small' | 'default' | 'large' } = $props();

	const sizes = {
		small: { icon: 20, text: 'text-lg' },
		default: { icon: 28, text: 'text-2xl' },
		large: { icon: 36, text: 'text-3xl' }
	};

	const s = $derived(sizes[size]);
</script>

<a href="/" class="flex items-center gap-2 no-underline">
	<ShieldCheck size={s.icon} class="text-primary" />
	<span class={`${s.text} tracking-tight`}>
		<span class="font-bold text-primary">WOO</span><span class="font-normal text-neutral">Buddy</span>
	</span>
</a>
