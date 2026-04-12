<script lang="ts">
	import { page } from '$app/state';
</script>

<div style="max-width: 600px; margin: 4rem auto; padding: 2rem; font-family: monospace;">
	<h1>{page.status}</h1>
	<pre style="white-space: pre-wrap; background: #f5f5f5; padding: 1rem; border-radius: 8px;">{page.error?.message}</pre>
</div>
