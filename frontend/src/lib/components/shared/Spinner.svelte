<script lang="ts">
	let { size = 'md' }: { size?: 'sm' | 'md' | 'lg' } = $props();

	const sizes = {
		sm: 'h-6 w-6 border-2',
		md: 'h-8 w-8 border-2',
		lg: 'h-10 w-10 border-3'
	};
</script>

<div class="animate-spin rounded-full border-primary border-t-transparent {sizes[size]}"></div>
