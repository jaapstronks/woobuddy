<script lang="ts">
	import Logo from '$lib/components/shared/Logo.svelte';
	import { FolderOpen, Plus, Settings } from 'lucide-svelte';
	import { page } from '$app/state';

	let { children } = $props();

	const nav = [
		{ href: '/app', label: 'Dossiers', icon: FolderOpen },
		{ href: '/app/dossier', label: 'Nieuw dossier', icon: Plus }
	];
</script>

<div class="flex h-screen bg-bg">
	<!-- Sidebar -->
	<aside class="flex w-64 flex-col border-r border-gray-200 bg-white">
		<div class="border-b border-gray-100 px-6 py-5">
			<Logo size="small" />
		</div>

		<nav class="flex-1 px-3 py-4">
			{#each nav as item}
				{@const active = page.url.pathname === item.href}
				<a
					href={item.href}
					class="mb-1 flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors
						{active ? 'bg-landing-accent text-primary' : 'text-neutral hover:bg-gray-50 hover:text-gray-900'}"
				>
					<item.icon size={18} />
					{item.label}
				</a>
			{/each}
		</nav>

		<div class="border-t border-gray-100 px-3 py-4">
			<a
				href="/app"
				class="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-neutral hover:bg-gray-50 hover:text-gray-900"
			>
				<Settings size={18} />
				Instellingen
			</a>
		</div>
	</aside>

	<!-- Main content -->
	<main class="flex-1 overflow-auto">
		<div class="mx-auto max-w-6xl px-8 py-8">
			{@render children()}
		</div>
	</main>
</div>
