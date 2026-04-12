<script lang="ts">
	import '@shoelace-style/shoelace/dist/components/alert/alert.js';
	import '@shoelace-style/shoelace/dist/components/icon/icon.js';

	import type { Snippet } from 'svelte';

	interface Props {
		variant: 'danger' | 'warning' | 'success' | 'primary';
		closable?: boolean;
		open?: boolean;
		children: Snippet;
	}

	let { variant, closable = false, open = true, children }: Props = $props();

	const iconMap: Record<string, string> = {
		danger: 'exclamation-octagon',
		warning: 'exclamation-triangle',
		success: 'check2-circle',
		primary: 'info-circle'
	};
</script>

<sl-alert {variant} {open} {closable}>
	<sl-icon slot="icon" name={iconMap[variant]}></sl-icon>
	{@render children()}
</sl-alert>
